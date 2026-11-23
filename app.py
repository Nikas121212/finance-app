import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

from db import init_db, get_conn, INCOME_CATEGORIES, EXPENSE_CATEGORIES_BUSINESS, EXPENSE_CATEGORIES_PERSONAL
import logic
import advisor

st.set_page_config(page_title="Финансы тату-мастера", layout="wide")
init_db()

st.sidebar.title("💰 Мои финансы")
page = st.sidebar.radio(
    "Раздел",
    ["Дашборд", "Операции", "Долги и цели", "Советчик", "Экспорт"],
)

# ---------- ДАШБОРД ----------
if page == "Дашборд":
    st.title("Дашборд")

    balance = logic.get_balance()
    available = logic.get_available_balance()
    col1, col2, col3 = st.columns(3)
    col1.metric("Общий баланс", f"{balance:,.0f} ₽")
    col2.metric("Свободно (без учёта накоплений на цели)", f"{available:,.0f} ₽")
    col3.metric("Средний доход в неделю", f"{logic.get_average_weekly_income():,.0f} ₽")

    st.subheader("Доход по неделям")
    series = logic.get_weekly_income_series()
    if series.sum() == 0:
        st.info("Пока нет данных по доходу — добавьте операции в разделе «Операции».")
    else:
        fig = px.bar(x=series.index, y=series.values, labels={"x": "Неделя", "y": "Доход, ₽"})
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Расходы по категориям (последние 30 дней)")
    breakdown = logic.get_expense_breakdown()
    if breakdown.empty:
        st.info("Пока нет расходов за последние 30 дней.")
    else:
        fig2 = px.pie(breakdown, names="category", values="amount")
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Прогресс по целям")
    goals = logic.load_goals()
    for _, g in goals.iterrows():
        pct = min(g.saved_amount / g.target_amount, 1.0) if g.target_amount else 0
        st.write(f"**{g['name']}** — {g.saved_amount:,.0f} / {g.target_amount:,.0f} ₽")
        st.progress(pct)

    st.subheader("Прогноз на конец месяца")
    fc = logic.forecast_month_end()
    st.write(
        f"Заработано в этом месяце: **{fc['income_so_far']:,.0f} ₽**, потрачено: **{fc['expense_so_far']:,.0f} ₽**"
    )
    st.write(
        f"Прогноз дохода до конца месяца (по текущему темпу): **{fc['projected_additional_income']:,.0f} ₽** "
        f"за {fc['days_left']} дн."
    )
    net = fc["projected_month_net"]
    color = "🟢" if net >= 0 else "🔴"
    st.write(f"{color} Ожидаемый итог месяца: **{net:,.0f} ₽**")

    warnings = logic.dead_season_warning()
    if warnings:
        st.subheader("⚠️ Предупреждения")
        for w in warnings:
            st.warning(w)

# ---------- ОПЕРАЦИИ ----------
elif page == "Операции":
    st.title("Операции")

    tab1, tab2, tab3 = st.tabs(["Добавить", "История", "Шаблоны регулярных платежей"])

    with tab1:
        kind = st.radio("Тип операции", ["Доход", "Расход"], horizontal=True)
        if kind == "Доход":
            category = st.selectbox("Категория", INCOME_CATEGORIES)
        else:
            category = st.selectbox(
                "Категория", EXPENSE_CATEGORIES_BUSINESS + EXPENSE_CATEGORIES_PERSONAL
            )
        amount = st.number_input("Сумма, ₽", min_value=0.0, step=100.0)
        op_date = st.date_input("Дата", value=date.today())
        comment = st.text_input("Комментарий (необязательно)")

        if st.button("Сохранить операцию", type="primary"):
            if amount <= 0:
                st.error("Сумма должна быть больше нуля.")
            else:
                with get_conn() as conn:
                    conn.execute(
                        "INSERT INTO transactions (date, kind, category, amount, comment) VALUES (?, ?, ?, ?, ?)",
                        (
                            op_date.isoformat(),
                            "income" if kind == "Доход" else "expense",
                            category,
                            amount,
                            comment,
                        ),
                    )
                st.success("Операция добавлена.")
                st.rerun()

    with tab2:
        df = logic.load_transactions()
        if df.empty:
            st.info("Операций пока нет.")
        else:
            df_display = df.sort_values("date", ascending=False).copy()
            df_display["date"] = df_display["date"].dt.strftime("%Y-%m-%d")
            df_display["kind"] = df_display["kind"].map({"income": "Доход", "expense": "Расход"})
            st.dataframe(
                df_display[["id", "date", "kind", "category", "amount", "comment"]],
                use_container_width=True,
                hide_index=True,
            )
            del_id = st.number_input("ID операции для удаления", min_value=0, step=1)
            if st.button("Удалить операцию"):
                with get_conn() as conn:
                    conn.execute("DELETE FROM transactions WHERE id = ?", (del_id,))
                st.success(f"Операция {del_id} удалена (если существовала).")
                st.rerun()

    with tab3:
        templates = logic.load_templates()
        st.dataframe(templates, use_container_width=True, hide_index=True)
        st.write("Подтвердите применение шаблона как операцию за текущий месяц:")
        if not templates.empty:
            tpl_name = st.selectbox("Шаблон", templates["name"].tolist())
            tpl_row = templates[templates["name"] == tpl_name].iloc[0]
            tpl_amount = st.number_input("Сумма (можно скорректировать)", value=float(tpl_row["amount"]))
            if st.button("Применить шаблон как операцию"):
                with get_conn() as conn:
                    conn.execute(
                        "INSERT INTO transactions (date, kind, category, amount, comment) VALUES (?, ?, ?, ?, ?)",
                        (date.today().isoformat(), tpl_row["kind"], tpl_row["category"], tpl_amount, f"По шаблону: {tpl_name}"),
                    )
                st.success("Операция добавлена из шаблона.")
                st.rerun()

# ---------- ДОЛГИ И ЦЕЛИ ----------
elif page == "Долги и цели":
    st.title("Долги и цели")

    st.subheader("Я должен")
    debts = logic.load_debts()
    i_owe = debts[debts.direction == "i_owe"]
    if i_owe.empty:
        st.info("Долгов нет.")
    else:
        for _, d in i_owe.iterrows():
            status = "✅ закрыт" if d.closed else f"{d.amount:,.0f} ₽"
            st.write(f"**{d.counterparty}** — {status} ({d.comment})")
            if not d.closed:
                c1, c2 = st.columns([3, 1])
                new_amount = c1.number_input(
                    f"Остаток долга «{d.counterparty}»", value=float(d.amount), key=f"debt_{d.id}"
                )
                if c2.button("Обновить", key=f"upd_{d.id}"):
                    closed = 1 if new_amount <= 0 else 0
                    with get_conn() as conn:
                        conn.execute(
                            "UPDATE debts SET amount = ?, closed = ? WHERE id = ?",
                            (max(new_amount, 0), closed, d.id),
                        )
                    st.rerun()

    st.subheader("Мне должны")
    owed_to_me = debts[debts.direction == "owed_to_me"]
    if owed_to_me.empty:
        st.info("Записей нет.")
    else:
        for _, d in owed_to_me.iterrows():
            status = "✅ получено" if d.closed else f"{d.amount:,.0f} ₽"
            st.write(f"**{d.counterparty}** — {status} ({d.comment})")

    with st.expander("➕ Добавить долг"):
        direction = st.radio("Тип", ["Я должен", "Мне должны"], horizontal=True, key="debt_dir")
        counterparty = st.text_input("Кому / от кого")
        amount_d = st.number_input("Сумма", min_value=0.0, step=500.0, key="debt_amount")
        comment_d = st.text_input("Комментарий", key="debt_comment")
        if st.button("Добавить долг"):
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO debts (direction, counterparty, amount, date_created, comment, closed) VALUES (?, ?, ?, ?, ?, 0)",
                    (
                        "i_owe" if direction == "Я должен" else "owed_to_me",
                        counterparty,
                        amount_d,
                        date.today().isoformat(),
                        comment_d,
                    ),
                )
            st.success("Долг добавлен.")
            st.rerun()

    st.divider()
    st.subheader("Цели накоплений (по приоритету)")
    goals = logic.load_goals()
    for _, g in goals.iterrows():
        pct = min(g.saved_amount / g.target_amount, 1.0) if g.target_amount else 0
        st.write(f"**{g.priority}. {g['name']}** — {g.saved_amount:,.0f} / {g.target_amount:,.0f} ₽")
        st.progress(pct)
        new_saved = st.number_input(
            f"Накоплено на «{g['name']}»", value=float(g.saved_amount), key=f"goal_{g.id}"
        )
        if st.button(f"Обновить «{g['name']}»", key=f"goal_upd_{g.id}"):
            with get_conn() as conn:
                conn.execute("UPDATE goals SET saved_amount = ? WHERE id = ?", (new_saved, g.id))
            st.rerun()

    st.divider()
    st.subheader("Прогноз закрытия долгов и целей")
    eta_list, disposable_weekly = logic.forecast_goal_dates()
    st.write(f"Располагаемый остаток после обязательных трат: **{disposable_weekly:,.0f} ₽/нед.**")
    if disposable_weekly <= 0:
        st.warning("При текущем темпе дохода свободных средств на цели не остаётся.")
    for item in eta_list:
        if item.get("eta_date"):
            st.write(
                f"• {item['name']}: осталось {item['remaining']:,.0f} ₽ — "
                f"прогноз закрытия через ~{item['eta_weeks']} нед. (≈ {item['eta_date']})"
            )
        else:
            st.write(f"• {item['name']}: осталось {item['remaining']:,.0f} ₽ — прогноз недоступен (нет свободных средств)")

# ---------- СОВЕТЧИК ----------
elif page == "Советчик":
    st.title("Советчик")
    st.caption(
        "Советы строятся по правилам: приоритет долги → подушка → реклама → курс, "
        "с учётом обязательных трат (аренда, коммуналка, продукты)."
    )

    mode = st.radio(
        "Что нужно решить?",
        ["Куда распределить заработанную сумму", "На что потратить сумму с пользой"],
    )

    if mode == "Куда распределить заработанную сумму":
        amount_in = st.number_input("Сколько заработано, ₽", min_value=0.0, step=500.0)
        days_rent = st.number_input(
            "Через сколько дней следующий платёж аренды/коммуналки (если известно, иначе 0)",
            min_value=0, step=1, value=0,
        )
        if st.button("Получить совет", type="primary"):
            days_param = days_rent if days_rent > 0 else None
            text = advisor.advise_allocation(amount_in, days_param)
            st.text(text)
            advisor.save_advice("allocation", amount_in, text)

    else:
        amount_in = st.number_input("Сумма, которую хочется потратить, ₽", min_value=0.0, step=500.0)
        if st.button("Получить совет", type="primary"):
            text = advisor.advise_spending(amount_in)
            st.text(text)
            advisor.save_advice("spending", amount_in, text)

    st.divider()
    st.subheader("История советов")
    hist = advisor.load_advice_history()
    if hist.empty:
        st.info("Советов пока не было.")
    else:
        for _, row in hist.iterrows():
            with st.expander(f"{row['date']} — {row['question_type']} — {row['input_amount']:,.0f} ₽"):
                st.text(row["advice_text"])

# ---------- ЭКСПОРТ ----------
elif page == "Экспорт":
    st.title("Экспорт данных")
    st.write("Выгрузите данные, чтобы перенести их на платный хостинг в будущем.")

    transactions = logic.load_transactions()
    goals = logic.load_goals()
    debts = logic.load_debts()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button(
            "Скачать операции (CSV)",
            transactions.to_csv(index=False).encode("utf-8-sig"),
            file_name="transactions.csv",
        )
    with col2:
        st.download_button(
            "Скачать цели (CSV)",
            goals.to_csv(index=False).encode("utf-8-sig"),
            file_name="goals.csv",
        )
    with col3:
        st.download_button(
            "Скачать долги (CSV)",
            debts.to_csv(index=False).encode("utf-8-sig"),
            file_name="debts.csv",
        )

    all_data = {
        "transactions": transactions.to_dict(orient="records"),
        "goals": goals.to_dict(orient="records"),
        "debts": debts.to_dict(orient="records"),
    }
    import json
    st.download_button(
        "Скачать всё в одном файле (JSON)",
        json.dumps(all_data, default=str, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name="finance_export.json",
    )
