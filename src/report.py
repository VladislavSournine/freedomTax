def generate_instruction(tax_result: dict, tax_year: int) -> str:
    div_uah = tax_result["dividend_income_uah"]
    other_uah = tax_result["other_income_uah"]
    foreign_income_total = round(div_uah + other_uah, 2)
    pdfo_foreign = round(tax_result["pdfo_dividends"] + tax_result["pdfo_other"], 2)
    vz_foreign = round(tax_result["vz_dividends"] + tax_result["vz_other"], 2)

    lines = [
        f"=== ІНСТРУКЦІЯ ДО ДЕКЛАРАЦІЇ ЗА {tax_year} РІК ===",
        "",
        "Сайт: cabinet.tax.gov.ua → Декларація про майновий стан і доходи",
        "",
        "━" * 60,
        "КРОК II — Розділ II (Доходи)",
        "━" * 60,
        "",
        "▶ Рядок 10.10 — Доходи з джерел за межами України",
        "  (сюди йдуть і дивіденди, і cashback від брокера)",
        "  r01010g2s  Країна та валюта:  США, долар США (USD)",
        f"  r01010g3   Сума доходу:      {foreign_income_total:>12.2f} грн",
        f"             ↳ для довідки: дивіденди {div_uah:.2f} + cashback {other_uah:.2f} = {foreign_income_total:.2f}",
        f"  r01010g6   ПДФО до сплати:  {pdfo_foreign:>12.2f} грн",
        f"  r01010g7   ВЗ до сплати:    {vz_foreign:>12.2f} грн",
        "",
    ]

    has_trades = tax_result["gross_profit_uah"] != 0.0

    if tax_result["net_profit_uah"] > 0:
        lines += [
            "▶ Рядок 10.8 — Інвестиційний прибуток (заповнюється автоматично з Ф1)",
            f"  r0108g3   Сума прибутку:    {tax_result['net_profit_uah']:>12.2f} грн",
            f"  r0108g6   ПДФО до сплати:  {tax_result['pdfo_trades']:>12.2f} грн",
            f"  r0108g7   ВЗ до сплати:    {tax_result['vz_trades']:>12.2f} грн",
            "",
        ]
    elif has_trades:
        lines += [
            "▶ Рядок 10.8 — Інвестиційний прибуток: 0.00 грн",
            "  (збиток — рядок буде 0, але Ф1 все одно заповнюється)",
            "",
        ]
    else:
        lines += [
            "▶ Рядок 10.8 — Інвестиційний прибуток: 0.00 грн",
            "  (продажів не було — рядок не заповнюється)",
            "",
        ]

    lines += [
        "━" * 60,
        "КРОК 9 — Додаток Ф1 (тільки якщо були продажі ЦП)",
        "━" * 60,
        "",
    ]

    if has_trades:
        lines += [
            "  Натисніть '+' для кожного тікера і введіть:",
            "  t1rxxxxg2  Вид активу: 'Інвестиційні активи з джерел за межами України'",
            "  t1rxxxxg3s Найменування: назва тікера (наприклад BAC.US)",
            "  t1rxxxxg4  Сума доходу від продажу (грн)",
            "  t1rxxxxg5  Сума витрат на придбання + комісії (грн)",
            "  t1rxxxxg6  Фінансовий результат (грн, від'ємне — зі знаком −)",
            "",
            "  Рядок r042g6 — ПДФО до самостійної сплати (розраховується автоматично)",
            "  Рядок r052g6 — ВЗ до самостійної сплати (розраховується автоматично)",
            "",
            "  Детальна таблиця значень — дивись файл f1_table.txt",
        ]
    else:
        lines += [
            "  Продажів не було — додаток Ф1 не заповнюється.",
        ]

    lines += [
        "",
        "━" * 60,
        "ПІДСУМОК ПОДАТКІВ ДО СПЛАТИ",
        "━" * 60,
        "",
        f"  ПДФО (іноземні доходи):          {pdfo_foreign:>12.2f} грн  ← r01010g6",
        f"  ПДФО (торгівля, з Ф1):           {tax_result['pdfo_trades']:>12.2f} грн  ← r042g6",
        f"  ПДФО разом:                      {tax_result['pdfo_total']:>12.2f} грн",
        "",
        f"  ВЗ (іноземні доходи):            {vz_foreign:>12.2f} грн  ← r01010g7",
        f"  ВЗ (торгівля, з Ф1):             {tax_result['vz_trades']:>12.2f} грн  ← r052g6",
        f"  ВЗ разом:                        {tax_result['vz_total']:>12.2f} грн",
        "",
        f"  ══ ПОДАТОК ДО СПЛАТИ:            {round(tax_result['pdfo_total'] + tax_result['vz_total'], 2):>12.2f} грн",
        "",
        "Примітки:",
        "  • Дивіденди від US-акцій НЕ вносяться в рядок 10.4",
        "    (10.4 — лише дивіденди від українських компаній)",
        "  • Збитки від торгівлі зараховуються в поточному році (ПКУ ст.170.2),",
        "    але НЕ переносяться на наступний рік",
        "  • Ефективна ставка ПДФО на дивіденди = 9% (з урахуванням US WHT кредиту)",
    ]
    return "\n".join(lines)


def generate_f1_table(positions: list, tax_year: int) -> str:
    # Group positions by ticker
    groups: dict = {}
    for pos in positions:
        ticker = pos["ticker"]
        if ticker not in groups:
            groups[ticker] = {
                "proceeds_uah": 0.0,
                "expenses_uah": 0.0,
                "profit_uah": 0.0,
            }
        groups[ticker]["proceeds_uah"] += pos["proceeds_uah"]
        groups[ticker]["expenses_uah"] += (
            pos["cost_uah"] + pos["buy_commission_uah"] + pos["sell_commission_uah"]
        )
        groups[ticker]["profit_uah"] += pos["profit_uah"]

    header_line = f"=== ТАБЛИЦЯ ДЛЯ ФОРМИ Ф1 (cabinet.tax.gov.ua) ЗА {tax_year} РІК ==="

    if not groups:
        lines = [
            header_line,
            "",
            "Закритих позицій за рік немає (відсутні дані для Ф1).",
        ]
        return "\n".join(lines)

    intro_lines = [
        header_line,
        "",
        "Для кожного рядка нижче натисніть \"+\" у формі Ф1 і введіть:",
        "  - Тип активу: ЗАВЖДИ обирайте \"Інвестиційні активи з джерел за межами України\"",
        "  - Найменування: вказано нижче",
        "  - Сума доходу (t1rxxxxg4), Сума витрат (t1rxxxxg5), Фін. результат (t1rxxxxg6)",
        "",
    ]

    # Column widths (content only, without border characters)
    w_num = 3       # "  #"  → right-aligned in 3 chars, padded to 4 with spaces
    w_name = 44     # ticker name column
    w_num_col = 12  # numeric columns

    def fmt_num(val: float) -> str:
        return f"{val:>12.2f}"

    def fmt_name(name: str) -> str:
        return f" {name:<{w_name - 1}}"

    border_top    = "┌" + "─" * 4 + "┬" + "─" * w_name + "┬" + "─" * w_num_col + "┬" + "─" * w_num_col + "┬" + "─" * w_num_col + "┐"
    border_mid    = "├" + "─" * 4 + "┼" + "─" * w_name + "┼" + "─" * w_num_col + "┼" + "─" * w_num_col + "┼" + "─" * w_num_col + "┤"
    border_bot    = "└" + "─" * 4 + "┴" + "─" * w_name + "┴" + "─" * w_num_col + "┴" + "─" * w_num_col + "┴" + "─" * w_num_col + "┘"

    def make_row(num_str: str, name: str, g4: float, g5: float, g6: float) -> str:
        num_cell = f" {num_str:>2} "
        name_cell = fmt_name(name)
        return f"│{num_cell}│{name_cell}│{fmt_num(g4)}│{fmt_num(g5)}│{fmt_num(g6)}│"

    header_row = f"│{'  #':^4}│{' Найменування (t1rxxxxg3s)':<{w_name}}│{'  Дохід (г4)':^{w_num_col}}│{' Витрати (г5)':^{w_num_col}}│{' Результат г6':^{w_num_col}}│"

    table_lines = [border_top, header_row, border_mid]

    total_proceeds = 0.0
    total_expenses = 0.0
    total_profit = 0.0

    for idx, (ticker, data) in enumerate(groups.items(), start=1):
        row = make_row(str(idx), ticker, data["proceeds_uah"], data["expenses_uah"], data["profit_uah"])
        table_lines.append(row)
        total_proceeds += data["proceeds_uah"]
        total_expenses += data["expenses_uah"]
        total_profit += data["profit_uah"]

    table_lines.append(border_mid)
    total_row = make_row("", "УСЬОГО (авто)", total_proceeds, total_expenses, total_profit)
    table_lines.append(total_row)
    table_lines.append(border_bot)

    footer_lines = [
        "",
        "Примітка: від'ємний фін. результат вводиться зі знаком \"-\"",
    ]

    all_lines = intro_lines + table_lines + footer_lines
    return "\n".join(all_lines)
