from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, serializers, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView
from users.models import CustomUser
from users.serializers import CustomUserSerializer
from .email_service import EmailService
from .models import InterestedParticipant, Project, Session
from .serializers import (
    InterestedParticipantSerializer,
    ProjectSerializer,
    SessionDetailSerializer,
    SessionParticipantSerializer,
    SessionSerializer,
)
from .services import (
    DeveloperSuggestionService,
    InvitationService,
    SessionCreationService,
    SessionSuggestionService,
    InterestNotificationService,
    ConfirmationNotificationService,
)


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]


class ProjectCreateView(generics.CreateAPIView):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class SessionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    queryset = Session.objects.all()
    serializer_class = SessionSerializer

    def perform_create(self, serializer):
        project_id = self.request.data.get("project")
        if not project_id:
            raise serializers.ValidationError(
                "Project ID is required to create a session."
            )

        if not Project.objects.filter(id=project_id).exists():
            raise serializers.ValidationError("Project does not exist.")

        session_data = serializer.validated_data

        session = SessionCreationService.handle_create_session(
            self.request.user, project_id, session_data
        )
        serializer.instance = session

    def update(self, request, *args, **kwargs):
        print("Request Data:", request.data)
        response = super().update(request, *args, **kwargs)
        print("Response Data:", response.data)
        return response


class SessionsByProjectView(generics.ListAPIView):
    serializer_class = SessionSerializer

    def get_queryset(self):
        project_id = self.kwargs["project_id"]
        return Session.objects.filter(project__id=project_id)


class ConfirmParticipantView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        try:
            session = get_object_or_404(Session, id=session_id)

            if session.host != request.user:
                raise PermissionError("Only the host can confirm participants.")

            developer_username = request.data.get("username")
            if not developer_username:
                raise ValueError("Developer username is required.")

            developer = get_object_or_404(CustomUser, username=developer_username)

            if session.participants.count() >= session.participant_limit > 0:
                raise ValueError("Participant limit reached.")

            session.participants.add(developer)

            confirmation_service = ConfirmationNotificationService(session, developer)
            confirmation_service.send_confirmation()

            return Response(
                {
                    "message": f"Developer {developer.username} has been confirmed for the session."
                },
                status=status.HTTP_200_OK,
            )

        except PermissionError as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response(
                {"error": "An unexpected error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class InterestedParticipantViewSet(viewsets.ModelViewSet):
    queryset = InterestedParticipant.objects.all()
    serializer_class = InterestedParticipantSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        try:
            session_id = self.request.data.get("session")
            if not session_id:
                raise ValidationError("Session ID is required.")

            session = get_object_or_404(Session, id=session_id)

            if InterestedParticipant.objects.filter(
                    user=self.request.user, session=session
            ).exists():
                raise ValidationError("You are already interested in this session.")

            interested_participant = serializer.save(user=self.request.user)

            notification_service = InterestNotificationService(session, self.request.user)
            notification_service.send_notification()

            return Response(
                {
                    "message": "You have successfully expressed interest in this session.",
                    "participant": InterestedParticipantSerializer(
                        interested_participant
                    ).data,
                },
                status=status.HTTP_201_CREATED,
            )

        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_409_CONFLICT)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"], url_path="interested-users")
    def get_interested_users(self, request, pk=None):
        session = get_object_or_404(Session, id=pk)
        interested_participants = InterestedParticipant.objects.filter(
            session=session
        ).select_related("user")

        users = [participant.user for participant in interested_participants]
        serializer = CustomUserSerializer(users, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)


class CheckUserInterestView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        try:
            session = get_object_or_404(Session, id=session_id)

            is_interested = InterestedParticipant.objects.filter(
                user=request.user, session=session
            ).exists()

            return Response({"is_interested": is_interested}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
def get_suggested_developers(request, session_id):
    try:
        session = Session.objects.get(id=session_id)
        suggestion_service = DeveloperSuggestionService(session)
        suggested_developers = suggestion_service.get_suggested_developers()
        serializer = CustomUserSerializer(suggested_developers, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)

    except Session.DoesNotExist:
        return Response(
            {"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
def invite_developer_to_session(request, session_id, developer_id):
    try:
        session = Session.objects.get(id=session_id)
        developer = CustomUser.objects.get(id=developer_id)
        invitation_service = InvitationService(session, developer)
        invitation_service.send_invitation()

        return Response(
            {"message": "Invitation sent successfully"}, status=status.HTTP_200_OK
        )

    except Session.DoesNotExist:
        return Response(
            {"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except CustomUser.DoesNotExist:
        return Response(
            {"error": "Developer not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except ValidationError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CheckUserParticipationView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id, user_id):
        try:
            session = get_object_or_404(Session, id=session_id)

            user = get_object_or_404(CustomUser, id=user_id)

            is_participant = session.participants.filter(id=user.id).exists()

            return Response(
                {"is_participant": is_participant}, status=status.HTTP_200_OK
            )

        except Session.DoesNotExist:
            return Response(
                {"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND
            )

        except CustomUser.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        except Exception as e:
            return Response(
                {"error": f"An unexpected error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@api_view(["GET"])
def get_suggested_sessions_for_user(request):
    try:
        user = request.user
        session_suggestion_service = SessionSuggestionService(user)
        suggested_sessions = session_suggestion_service.get_suggested_sessions()
        serializer = SessionSerializer(suggested_sessions, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)

    except ValidationError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserHostedSessionsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SessionSerializer

    def get_queryset(self):
        user = self.request.user
        return Session.objects.filter(host=user)


class UserParticipatingSessionsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SessionSerializer

    def get_queryset(self):
        user = self.request.user
        return Session.objects.filter(participants=user)


class UserInterestedSessionsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SessionSerializer

    def get_queryset(self):
        user = self.request.user
        interested_sessions_ids = InterestedParticipant.objects.filter(
            user=user
        ).values_list("session_id", flat=True)
        return Session.objects.filter(id__in=interested_sessions_ids)


class UserSessionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        hosted_sessions = Session.objects.filter(host=user)
        participating_sessions = Session.objects.filter(participants=user)
        interested_sessions_ids = InterestedParticipant.objects.filter(
            user=user
        ).values_list("session_id", flat=True)
        interested_sessions = Session.objects.filter(id__in=interested_sessions_ids)

        hosted_serializer = SessionSerializer(hosted_sessions, many=True)
        participating_serializer = SessionSerializer(participating_sessions, many=True)
        interested_serializer = SessionSerializer(interested_sessions, many=True)

        return Response(
            {
                "hosted_sessions": hosted_serializer.data,
                "participating_sessions": participating_serializer.data,
                "interested_sessions": interested_serializer.data,
            }
        )
