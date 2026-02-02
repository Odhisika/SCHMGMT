import os
import django
import sys
from datetime import time

# Set up Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from timetable.models import Period
from school.models import School

def seed_periods():
    school = School.objects.first()
    if not school:
        print("No school found.")
        return

    periods_data = [
        {"name": "Period 1", "type": "LESSON", "start": time(8, 0), "end": time(8, 40), "order": 1},
        {"name": "Period 2", "type": "LESSON", "start": time(8, 40), "end": time(9, 20), "order": 2},
        {"name": "Short Break", "type": "BREAK", "start": time(9, 20), "end": time(9, 40), "order": 3},
        {"name": "Period 3", "type": "LESSON", "start": time(9, 40), "end": time(10, 20), "order": 4},
        {"name": "Period 4", "type": "LESSON", "start": time(10, 20), "end": time(11, 0), "order": 5},
        {"name": "Long Break", "type": "BREAK", "start": time(11, 0), "end": time(12, 0), "order": 6},
        {"name": "Period 5", "type": "LESSON", "start": time(12, 0), "end": time(12, 40), "order": 7},
        {"name": "Period 6", "type": "LESSON", "start": time(12, 40), "end": time(13, 20), "order": 8},
    ]

    for p in periods_data:
        Period.objects.get_or_create(
            school=school,
            order=p["order"],
            defaults={
                "name": p["name"],
                "period_type": p["type"],
                "start_time": p["start"],
                "end_time": p["end"],
            }
        )
    
    print(f"Successfully seeded {len(periods_data)} periods for {school.name}")

if __name__ == "__main__":
    seed_periods()
