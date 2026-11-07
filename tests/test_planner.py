"""Pure-logic tests for the planner (no database needed)."""
import unittest
from datetime import date
from decimal import Decimal

from services import planner_service as P


class RecurrenceTests(unittest.TestCase):
    def test_monthly_clamps_to_month_end_and_recovers(self):
        self.assertEqual(P.next_occurrence('monthly', 1, 31, date(2026, 1, 31)), date(2026, 2, 28))
        self.assertEqual(P.next_occurrence('monthly', 1, 31, date(2026, 2, 28)), date(2026, 3, 31))

    def test_monthly_interval_crosses_year(self):
        self.assertEqual(P.next_occurrence('monthly', 3, 15, date(2026, 11, 15)), date(2027, 2, 15))

    def test_weekly_and_yearly(self):
        self.assertEqual(P.next_occurrence('weekly', 2, 1, date(2026, 1, 1)), date(2026, 1, 15))
        self.assertEqual(P.next_occurrence('yearly', 1, 29, date(2024, 2, 29)), date(2025, 2, 28))


class BillStageTests(unittest.TestCase):
    def test_stages_escalate_as_due_date_passes(self):
        stages = [P._bill_stage(d, 3) for d in (10, 3, 2, 1, 0, -1, -3, -7)]
        self.assertEqual(stages, [0, 1, 1, 2, 3, 3, 4, 5])

    def test_zero_remind_days_only_fires_on_due_day(self):
        self.assertEqual(P._bill_stage(1, 0), 2)   # "tomorrow" still counts as stage 2
        self.assertEqual(P._bill_stage(2, 0), 0)


class BudgetStatusTests(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(P._budget_status(Decimal('700'), Decimal('1000'), 80), (70.0, 'ok'))
        self.assertEqual(P._budget_status(Decimal('800'), Decimal('1000'), 80), (80.0, 'warning'))
        self.assertEqual(P._budget_status(Decimal('1000'), Decimal('1000'), 80), (100.0, 'over'))


class GoalViewTests(unittest.TestCase):
    goal = {'id': 1, 'target_amount': Decimal('1000'), 'target_date': date(2027, 3, 1)}

    def test_monthly_amount_needed(self):
        view = P._goal_view(self.goal, [{'amount': Decimal('250')}], today=date(2026, 11, 1))
        self.assertEqual(view['saved'], 250)
        self.assertEqual(view['percent'], 25.0)
        self.assertEqual(view['months_left'], 4)          # 120 days -> 4 months, rounded up
        self.assertEqual(view['monthly_needed'], 187.5)

    def test_completed_and_overdue(self):
        done = P._goal_view(self.goal, [{'amount': Decimal('1000')}], today=date(2026, 11, 1))
        self.assertTrue(done['completed'])
        self.assertIsNone(done['monthly_needed'])
        late = P._goal_view(self.goal, [], today=date(2027, 4, 1))
        self.assertTrue(late['overdue'])


class ValidationTests(unittest.TestCase):
    def test_money(self):
        self.assertEqual(P._money('1,250.5', 'x'), Decimal('1250.50'))
        for bad in ('abc', '0', '-3', ''):
            with self.assertRaises(P.ValidationError):
                P._money(bad, 'x')

    def test_rule_requires_description_and_valid_dates(self):
        with self.assertRaises(P.ValidationError):
            P._rule_from_payload({'description': ' ', 'amount': 5, 'start_date': '2026-01-01'})
        with self.assertRaises(P.ValidationError):
            P._rule_from_payload({'description': 'x', 'amount': 5, 'start_date': '2026-02-01', 'end_date': '2026-01-01'})

    def test_topic_validation(self):
        self.assertTrue(P.TOPIC_RE.match('my-topic_1'))
        self.assertFalse(P.TOPIC_RE.match('bad topic'))


if __name__ == '__main__':
    unittest.main()
