
from rest_framework import viewsets
from .models import CalendarEvent
from .serializers import CalendarEventSerializer
from django.shortcuts import render

def calendar_view(request):
    return render(request, 'modulocalendar/calendar.html')

from rest_framework import viewsets, permissions

class CalendarEventViewSet(viewsets.ModelViewSet):
    serializer_class = CalendarEventSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CalendarEvent.objects.filter(user=self.request.user)
