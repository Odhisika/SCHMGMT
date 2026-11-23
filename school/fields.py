from django import forms
from django.core.exceptions import ValidationError
from django.db import models


class FlexibleTypedChoiceField(forms.TypedChoiceField):
    """Choice field that tolerates values outside the model's default choices.

    App forms replace ``choices`` with school-aware options; once they do,
    normal choice validation applies again.  Admin forms keep the model's
    static choices but can still edit records with custom values.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._model_choices = list(self.choices)

    def validate(self, value):
        if list(self.choices) != self._model_choices:
            return super().validate(value)

        if self.required and value in self.empty_values:
            raise ValidationError(
                self.error_messages["required"], code="required"
            )


class FlexibleChoiceCharField(models.CharField):
    """A ``CharField`` that keeps choices for display but accepts custom values.

    Divisions and class levels are configured per school at runtime.  Keeping
    ``choices`` on the model preserves ``get_FOO_display()``, admin labels and
    generated form dropdowns, while this override prevents model validation
    from rejecting values that are valid for one school but not another.
    Form fields still validate against the school-aware choices supplied by
    the views/forms.
    """

    def validate(self, value, model_instance):
        if not self.editable:
            return

        if value is None and not self.null:
            raise ValidationError(self.error_messages["null"], code="null")

        if not self.blank and value in self.empty_values:
            raise ValidationError(self.error_messages["blank"], code="blank")

    def formfield(self, **kwargs):
        """Use a choice field that tolerates school-specific values.

        App forms replace these choices with school-aware ones.  Admin forms,
        which have no school context, keep the built-in dropdown but can still
        edit records whose stored value is a custom division or level.
        """
        kwargs.setdefault("choices_form_class", FlexibleTypedChoiceField)
        return super().formfield(**kwargs)
