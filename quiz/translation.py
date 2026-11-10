from modeltranslation.translator import register, TranslationOptions
from .models import Quiz, Question, Choice, MCQuestion, EssayQuestion


@register(Quiz)
class QuizTranslationOptions(TranslationOptions):
    fields = (
        "title",
        "description",
    )
    empty_values = None


@register(Question)
class QuestionTranslationOptions(TranslationOptions):
    fields = (
        "content",
        "explanation",
    )
    empty_values = None


@register(Choice)
class ChoiceTranslationOptions(TranslationOptions):
    fields = ("choice_text",)
    empty_values = None


@register(MCQuestion)
class MCQuestionTranslationOptions(TranslationOptions):
    pass


@register(EssayQuestion)
class EssayQuestionTranslationOptions(TranslationOptions):
    """Essay questions inherit translatable fields from ``Question``.

    Registering the subclass (with no extra fields) keeps modeltranslation's
    constructor/save hooks working, matching the existing MCQuestion setup.
    """
    pass
