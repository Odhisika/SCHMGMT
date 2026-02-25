from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "accounts"

    def ready(self) -> None:
        from django.db.models.signals import post_save, pre_save
        from .models import User, Student
        from .signals import (
            post_save_account_receiver,
            auto_enroll_student_in_courses,
            track_level_changes,
            handle_level_change
        )
        
        # Connect User post_save signal
        post_save.connect(post_save_account_receiver, sender=User)
        
        # Connect Student auto-enrollment signals
        post_save.connect(auto_enroll_student_in_courses, sender=Student)
        pre_save.connect(track_level_changes, sender=Student)
        post_save.connect(handle_level_change, sender=Student)

        return super().ready()
