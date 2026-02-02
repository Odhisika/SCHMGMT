from .utils import (
    generate_student_credentials,
    generate_lecturer_credentials,
    send_new_account_email,
)


def post_save_account_receiver(instance=None, created=False, *args, **kwargs):
    """
    Send email notification
    """
    # Logic moved to forms/views to ensure username uniqueness before saving
    # and prevent IntegrityError on the first save.
    pass
    # if created:
    #     if instance.is_student:
    #         username, password = generate_student_credentials()
    #         instance.username = username
    #         instance.set_password(password)
    #         instance.save()
    #         # Send email with the generated credentials
    #         send_new_account_email(instance, password)

    #     if instance.is_lecturer:
    #         username, password = generate_lecturer_credentials()
    #         instance.username = username
    #         instance.set_password(password)
    #         instance.save()
    #         # Send email with the generated credentials
    #         send_new_account_email(instance, password)
