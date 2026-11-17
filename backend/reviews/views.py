from django.db import transaction
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from agent.loaders import file_to_text
from agent.nodes import validate_decisions
from agent.schemas import Finding
from reviews import services
from reviews.models import Checklist, Review, ReviewFile
from reviews.serializers import (
    ChecklistSerializer,
    DecisionsSerializer,
    ReviewCreateSerializer,
    ReviewDetailSerializer,
    ReviewListSerializer,
)


class ChecklistViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Checklist.objects.all()
    serializer_class = ChecklistSerializer
    lookup_field = "slug"


class ReviewViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Review.objects.select_related("checklist").prefetch_related("files")

    def get_serializer_class(self):
        return ReviewListSerializer if self.action == "list" else ReviewDetailSerializer

    def create(self, request: Request) -> Response:
        serializer = ReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            review = Review.objects.create(
                candidate_name=data["candidate_name"],
                checklist=data["checklist"],
                requirements=data["checklist"].items,
            )
            for upload in data.get("files", []):
                content = upload.read()
                upload.seek(0)
                review_file = ReviewFile(review=review, name=upload.name, file=upload)
                try:
                    review_file.text = file_to_text(upload.name, content)
                except Exception as exc:
                    # The workflow will report the file as unreadable.
                    review_file.extraction_error = str(exc)
                review_file.save()

        services.start_review(review)
        review.refresh_from_db()
        return Response(
            ReviewDetailSerializer(review, context={"request": request}).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["get"], url_path=r"files/(?P<file_id>\d+)/download")
    def download(self, request: Request, pk=None, file_id=None) -> FileResponse:
        review_file = self.get_object().files.get(pk=file_id)
        return FileResponse(review_file.file.open("rb"), as_attachment=False, filename=review_file.name)

    @action(detail=True, methods=["post"])
    def decisions(self, request: Request, pk=None) -> Response:
        review = self.get_object()
        serializer = DecisionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decisions = serializer.validated_data["decisions"]

        if review.status != Review.Status.WAITING_FOR_HUMAN:
            return Response(
                {"detail": f"Review is {review.status}, not waiting for a decision"},
                status=status.HTTP_409_CONFLICT,
            )

        # Same validation as the workflow node, so a bad answer is refused before resuming.
        doubtful = [Finding.model_validate(f) for f in (review.pending_review or {}).get("findings", [])]
        try:
            validate_decisions(doubtful, decisions)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            services.resume_review(review, decisions)
        except services.ReviewStateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        review.refresh_from_db()
        return Response(
            ReviewDetailSerializer(review, context={"request": request}).data, status=status.HTTP_202_ACCEPTED
        )
