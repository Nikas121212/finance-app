from datetime import date
from db import get_conn
from logic import get_allocation_order, MANDATORY_TOTAL, get_average_weekly_income, load_goals


def save_advice(question_type, input_amount, advice_text):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO advice_history (date, question_type, input_amount, advice_text) VALUES (?, ?, ?, ?)",
            (date.today().isoformat(), question_type, input_amount, advice_text),
        )


def load_advice_history():
    with get_conn() as conn:
        import pandas as pd
        return pd.read_sql_query("SELECT * FROM advice_history ORDER BY id DESC", conn)


def advise_allocation(amount, days_until_rent=None):
    """Советует, как распределить заработанную сумму N по приоритету."""
    order = get_allocation_order()
    weekly_mandatory = MANDATORY_TOTAL / 4.33
    lines = []
    remaining = amount

    reserve_note = ""
    if days_until_rent is not None and days_until_rent <= 14:
        rent_reserve = min(remaining, weekly_mandatory * 2)
        reserve_note = (
            f"Аренда/обязательные платежи близко ({days_until_rent} дн.) — "
            f"сначала держите в уме ~{rent_reserve:,.0f} ₽ на них, не вкладывайте всё в цели."
        )
        lines.append(reserve_note)

    if not order:
        lines.append(
            f"Долги закрыты, все цели достигнуты — {amount:,.0f} ₽ свободны. "
            f"Можно инвестировать в развитие (оборудование, реклама) или в личную подушку сверх плана."
        )
        return "\n".join(lines)

    lines.append(f"Распределение {amount:,.0f} ₽ по приоритету (долги → подушка → реклама → курс):")
    for item in order:
        if remaining <= 0:
            break
        alloc = min(remaining, item["remaining"])
        remaining -= alloc
        lines.append(f"  • {item['name']}: +{alloc:,.0f} ₽ (осталось закрыть {item['remaining'] - alloc:,.0f} ₽)")

    if remaining > 0:
        lines.append(f"После закрытия всех целей остаётся {remaining:,.0f} ₽ — свободные средства.")

    return "\n".join(lines)


def advise_spending(amount):
    """Советует, на что потратить свободную сумму с пользой."""
    order = get_allocation_order()
    avg_weekly = get_average_weekly_income()
    weekly_mandatory = MANDATORY_TOTAL / 4.33

    lines = [f"Вопрос: куда потратить {amount:,.0f} ₽ с пользой."]

    if avg_weekly < weekly_mandatory * 1.2:
        lines.append(
            "Текущий доход близок к уровню обязательных трат или ниже — "
            "приоритет: не тратить на необязательное, лучше закрыть долги/подушку."
        )

    if order:
        top = order[0]
        if amount >= top["remaining"]:
            lines.append(f"Этой суммой можно полностью закрыть «{top['name']}» ({top['remaining']:,.0f} ₽).")
        else:
            pct = amount / top["remaining"] * 100
            lines.append(
                f"Приоритет сейчас — «{top['name']}» (осталось {top['remaining']:,.0f} ₽). "
                f"{amount:,.0f} ₽ закроют {pct:.0f}% этой цели."
            )
        lines.append(
            "Если сумма не критична для жизни и хочется вложить в дело — "
            "расходники/оборудование допустимы только после текущего приоритета, "
            "иначе это откладывает закрытие долгов/подушки."
        )
    else:
        lines.append(
            "Долги и все цели закрыты — сумму можно направить на развитие "
            "(реклама, оборудование, обучение) по своему выбору."
        )

    return "\n".join(lines)
