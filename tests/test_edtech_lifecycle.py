from datetime import date

from src.edtech_lifecycle import CourseDelivery, expiry_decision


def test_report_expires_after_the_learner_deadline_buffer():
    delivery = CourseDelivery("checkout", "learner-7", date(2026, 10, 20), "reports/learner-7.json")

    before_buffer = expiry_decision(delivery, date(2026, 10, 21))
    after_buffer = expiry_decision(delivery, date(2026, 10, 22))

    assert before_buffer.should_expire is False
    assert after_buffer.should_expire is True
    assert after_buffer.expires_on == date(2026, 10, 21)
