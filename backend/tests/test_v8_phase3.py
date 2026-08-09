from app.services.feedback_v8 import normalize_feedback_category
from app.services.projects_v8 import normalize_project_name


def test_normalize_project_name_trims_and_limits():
    value = normalize_project_name('   My    Vasuki    Project   ')
    assert value == 'My Vasuki Project'


def test_feedback_category_fallback():
    assert normalize_feedback_category('bad image') == 'bad_image'
    assert normalize_feedback_category('unknown category') == 'other'
