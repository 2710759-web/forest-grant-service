"""ЛесАналитика БПЛА — демонстрационная версия 1.1 (на основе исходного app.py).

Назначение: анализ *предварительно подготовленной* таблицы деревьев и отображение
их расположения поверх ортофотоплана. Программа не выполняет автоматическое
распознавание крон на изображениях и не заменяет официальную лесную таксацию.
"""

from datetime import date
from html import escape
from io import BytesIO
from pathlib import Path
import hashlib
import base64

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from PIL import Image, UnidentifiedImageError
import streamlit as st

st.set_page_config(page_title="ЛесАналитика БПЛА | ФСИ", page_icon="🌲", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
REQUIRED_COLUMNS = (
    "X", "Y", "Площадь кроны, м2", "Диаметр кроны, м",
    "Диаметр ствола, см", "Высота, м", "Объём ствола, м3",
)
CATEGORICAL_COLUMNS = ("Класс товарности", "Категория крупности", "Бонитет")
TOVARNOST_OPTIONS = ["I класс", "II класс", "III класс"]
SIZE_OPTIONS = ["Мелкомер", "Среднемер", "Крупномер", "Очень крупный"]
BONITET_OPTIONS = ["I", "II", "III", "IV", "V"]

# Упрощенные, иллюстративные коэффициенты исходного прототипа; не нормативные таблицы.
SPECIES_DATA = {
    "Сосна": {"bonitet_table": {"I": 28, "II": 24, "III": 20, "IV": 16, "V": 12}, "tovarnost": {"I класс": {"min_d": 24, "min_h": 20}, "II класс": {"min_d": 14, "min_h": 15}, "III класс": {"min_d": 0, "min_h": 0}}, "form_factor": 0.45, "density_norm": 35},
    "Ель": {"bonitet_table": {"I": 30, "II": 26, "III": 22, "IV": 18, "V": 14}, "tovarnost": {"I класс": {"min_d": 24, "min_h": 20}, "II класс": {"min_d": 14, "min_h": 15}, "III класс": {"min_d": 0, "min_h": 0}}, "form_factor": 0.42, "density_norm": 38},
    "Берёза": {"bonitet_table": {"I": 26, "II": 22, "III": 18, "IV": 14, "V": 10}, "tovarnost": {"I класс": {"min_d": 20, "min_h": 18}, "II класс": {"min_d": 12, "min_h": 12}, "III класс": {"min_d": 0, "min_h": 0}}, "form_factor": 0.40, "density_norm": 30},
    "Осина": {"bonitet_table": {"I": 28, "II": 24, "III": 20, "IV": 16, "V": 12}, "tovarnost": {"I класс": {"min_d": 22, "min_h": 18}, "II класс": {"min_d": 12, "min_h": 12}, "III класс": {"min_d": 0, "min_h": 0}}, "form_factor": 0.41, "density_norm": 32},
    "Лиственница": {"bonitet_table": {"I": 30, "II": 26, "III": 22, "IV": 18, "V": 14}, "tovarnost": {"I класс": {"min_d": 24, "min_h": 20}, "II класс": {"min_d": 14, "min_h": 15}, "III класс": {"min_d": 0, "min_h": 0}}, "form_factor": 0.44, "density_norm": 34},
}


def clean_dataframe(raw_df: pd.DataFrame, image_size: tuple[int, int]):
    """Проверяет таблицу и возвращает (очищенные данные, статистика отказов).

    Координаты X, Y — пиксели исходного изображения (нулевая точка вверху слева).
    """
    df = raw_df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("Отсутствуют обязательные столбцы: " + ", ".join(missing))
    if len(df) == 0:
        raise ValueError("В таблице нет строк с данными")

    for col in REQUIRED_COLUMNS:
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace("\u00a0", "", regex=False)
                .str.replace(" ", "", regex=False)
                .str.replace(",", ".", regex=False).str.strip(),
            errors="coerce",
        )
        df.loc[~np.isfinite(df[col]), col] = np.nan

    width, height = image_size
    finite_mask = df[list(REQUIRED_COLUMNS)].notna().all(axis=1)
    positive_mask = (
        (df["Диаметр кроны, м"] >= 0) &
        (df["Площадь кроны, м2"] >= 0) &
        (df["Диаметр ствола, см"] > 0) &
        (df["Высота, м"] > 0) &
        (df["Объём ствола, м3"] >= 0)
    )
    inside_mask = (
        df["X"].between(0, width - 1) & df["Y"].between(0, height - 1)
    )
    valid_mask = finite_mask & positive_mask & inside_mask
    stats = {
        "input_rows": int(len(df)),
        "missing_values": int((~finite_mask).sum()),
        "invalid_measurements": int((finite_mask & ~positive_mask).sum()),
        "outside_image": int((finite_mask & positive_mask & ~inside_mask).sum()),
        "rejected_rows": int((~valid_mask).sum()),
    }
    df = df.loc[valid_mask].copy().reset_index(drop=True)
    if df.empty:
        raise ValueError("После проверки не осталось корректных записей")
    if "Порода" in df.columns:
        df["Порода"] = df["Порода"].fillna("Не указана").astype(str).str.strip()
        df.loc[df["Порода"] == "", "Порода"] = "Не указана"
    if "ID" not in df.columns:
        df.insert(0, "ID", np.arange(1, len(df) + 1))
    return df, stats


def calculate_additional_params(df: pd.DataFrame, species: str | None = None) -> pd.DataFrame:
    """Производные *оценочные* показатели из исходного прототипа."""
    df = df.copy()
    sp = (df["Порода"] if "Порода" in df.columns else pd.Series(species, index=df.index))
    sp = sp.fillna("")
    df["g_сечения_м2"] = np.pi * (df["Диаметр ствола, см"] / 200.0) ** 2
    df["Видовое число"] = sp.map({k: v["form_factor"] for k, v in SPECIES_DATA.items()}).fillna(0.45)
    df["Объём_расчётный_м3"] = df["g_сечения_м2"] * df["Высота, м"] * df["Видовое число"]
    df["H/D ratio"] = df["Высота, м"] / (df["Диаметр ствола, см"] / 100.0)

    def tovarnost(row):
        props = SPECIES_DATA.get(sp.loc[row.name])
        if props:
            for cls, v in props["tovarnost"].items():
                if row["Диаметр ствола, см"] >= v["min_d"] and row["Высота, м"] >= v["min_h"]:
                    return cls
        return "III класс"

    def bonitet(row):
        props = SPECIES_DATA.get(sp.loc[row.name])
        if props:
            for cls, min_h in sorted(props["bonitet_table"].items(), key=lambda kv: kv[1], reverse=True):
                if row["Высота, м"] >= min_h:
                    return cls
        return "V"

    df["Класс товарности"] = df.apply(tovarnost, axis=1)
    df["Категория крупности"] = pd.cut(
        df["Диаметр ствола, см"], bins=[-np.inf, 8, 14, 26, np.inf],
        labels=SIZE_OPTIONS, right=False,
    ).astype(str)
    df["Бонитет"] = df.apply(bonitet, axis=1)

    def normalized(col):
        vals = df[col].astype(float)
        span = vals.max() - vals.min()
        return (vals - vals.min()) / span if span > 1e-12 else pd.Series(0.5, index=df.index)

    df["Индекс виталитета"] = (
        normalized("Высота, м") * 30 + normalized("Диаметр ствола, см") * 40 +
        normalized("Площадь кроны, м2") * 30
    ).round(1)
    df["Полнота_вклад"] = df["g_сечения_м2"]
    df["Запас_м3_га"] = df["Объём_расчётный_м3"]  # исходное имя: фактически объём ДЕРЕВА, не м³/га
    return df


def calculate_site_metrics(df: pd.DataFrame, image_size: tuple[int, int], gsd_m: float, species: str | None):
    """Площадь прямоугольного охвата *всего снимка*, базальная площадь и объём на га."""
    if gsd_m <= 0:
        raise ValueError("GSD должен быть положительным")
    width, height = image_size
    area_ha = width * height * gsd_m ** 2 / 10_000
    basal_area = float(df["g_сечения_м2"].sum())
    volume = float(df["Объём_расчётный_м3"].sum())
    basal_ha = basal_area / area_ha
    volume_ha = volume / area_ha
    if "Порода" in df.columns:
        prevalent = df["Порода"].mode().iloc[0]
    else:
        prevalent = species
    density_norm = SPECIES_DATA.get(prevalent, SPECIES_DATA["Сосна"])["density_norm"]
    return {
        "area_ha": float(area_ha), "basal_m2_total": basal_area,
        "basal_m2_ha": basal_ha, "volume_m3_total": volume,
        "volume_m3_ha": volume_ha,
        "relative_basal_percent": basal_ha / density_norm * 100 if density_norm else 0,
        "prevalent_species": prevalent or "Не указана",
    }


def apply_preset(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    """Выборка по ориентировочным, а не нормативно утверждённым критериям."""
    if mode == "Заготовка древесины (пример)":
        return df.loc[
            (df["Высота, м"] >= 20) & (df["Объём_расчётный_м3"] >= 1) &
            (df["Диаметр ствола, см"] >= 14) &
            df["Класс товарности"].isin(["I класс", "II класс"]) &
            df["Бонитет"].isin(["I", "II", "III"])
        ]
    if mode == "Молодняк (пример ухода)":
        return df.loc[
            df["Высота, м"].between(5, 15) &
            df["Диаметр ствола, см"].between(8, 20) &
            (df["Класс товарности"] == "III класс")
        ]
    return df.copy()


def image_as_data_uri(img: Image.Image) -> str:
    out = BytesIO()
    img.convert("RGB").save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode("ascii")


def build_excel_report(
    df: pd.DataFrame, selected: pd.DataFrame, metrics: dict,
    report_title: str, report_date: date, gsd_m: float, image_size: tuple[int, int],
    stats: dict,
) -> bytes:
    """Создаёт XLSX в памяти (нет временных файлов на хосте)."""
    result = BytesIO()
    with pd.ExcelWriter(result, engine="xlsxwriter") as writer:
        wb = writer.book
        fmt_header = wb.add_format({"bold": True, "font_color": "white", "bg_color": "#215C42", "border": 0})
        fmt_note = wb.add_format({"text_wrap": True, "valign": "top"})
        fmt_float = wb.add_format({"num_format": "0.000"})
        summary = pd.DataFrame([
            ("Название участка", report_title),
            ("Дата формирования", report_date.strftime("%d.%m.%Y")),
            ("Всего корректных деревьев", len(df)),
            ("Отобрано деревьев", len(selected)),
            ("Доля деревьев в выборке, %", round(len(selected) / len(df) * 100, 2)),
            ("Ширина изображения, пикс.", image_size[0]),
            ("Высота изображения, пикс.", image_size[1]),
            ("GSD, м/пиксель", gsd_m),
            ("Площадь охвата снимка, га", round(metrics["area_ha"], 4)),
            ("Сумма площадей сечений, м²", round(metrics["basal_m2_total"], 3)),
            ("Площадь сечений, м²/га", round(metrics["basal_m2_ha"], 3)),
            ("Расчётный запас на весь снимок, м³", round(metrics["volume_m3_total"], 3)),
            ("Расчётный запас, м³/га", round(metrics["volume_m3_ha"], 3)),
            ("Строк исключено при валидации", stats["rejected_rows"]),
            ("Примечание", "Площадь рассчитана для всего прямоугольника изображения; значения зависят от заданного GSD."),
            ("Методические ограничения", "Видовое число, класс товарности, бонитет и индекс виталитета оценочные. Бонитет без возраста не является нормативной оценкой."),
            ("Источник", "Таблица таксационных характеристик деревьев, предоставленная пользователем; программа не распознаёт деревья по фотографии."),
        ], columns=["Параметр", "Значение"])
        summary.to_excel(writer, sheet_name="Сводка", index=False)
        selected.to_excel(writer, sheet_name="Отобранные деревья", index=False)
        df.to_excel(writer, sheet_name="Все деревья", index=False)
        for field, sheetname in [
            ("Класс товарности", "Товарность"),
            ("Бонитет", "Бонитет"),
            ("Порода", "Породный состав"),
        ]:
            if field in selected.columns:
                values = selected[field].value_counts(dropna=False).rename_axis(field).reset_index(name="Количество")
                values.to_excel(writer, sheet_name=sheetname, index=False)
        for name, sheet in writer.sheets.items():
            sheet.freeze_panes(1, 0)
            sheet.set_row(0, 25, fmt_header)
            sheet.set_column(0, 0, 31)
            sheet.set_column(1, 24, 19, fmt_float if name != "Сводка" else None)
        writer.sheets["Сводка"].set_column(1, 1, 88, fmt_note)
    return result.getvalue()


st.markdown("""
<style>
.main-title {font-size:2.1rem; font-weight:700; color:#215C42; margin-bottom:.25rem}
.section-title {font-size:1.35rem; font-weight:600; margin:1rem 0}
</style>
""", unsafe_allow_html=True)
st.markdown('<div class="main-title">🌲 ЛесАналитика БПЛА</div>', unsafe_allow_html=True)
st.caption("Демонстрационный прототип анализа древостоев по заранее подготовленным данным аэрофотосъёмки")
st.info(
    "Проект реализован при поддержке Фонда содействия инновациям в рамках программы "
    "«Студенческий стартап» мероприятия «Платформа университетского "
    "технологического предпринимательства» федерального проекта «Технологии»"
)
logo_fsi = BASE_DIR / "logo_fsi.png"
logo_platform = BASE_DIR / "logo_platform.png"
if logo_fsi.is_file() and logo_platform.is_file():
    logocol1, logocol2, _ = st.columns([1, 1, 3])
    with logocol1:
        st.image(str(logo_fsi), width=190)
    with logocol2:
        st.image(str(logo_platform), width=190)
else:
    st.warning("Перед публичной демонстрацией ФСИ добавьте рядом с app.py официальные логотипы logo_fsi.png и logo_platform.png (пока не включены в комплект).")

with st.sidebar:
    st.header("📁 Исходные данные")
    demo_mode = st.checkbox("Использовать комплект демонстрационных данных", value=True)
    uploaded_image = None
    uploaded_table = None
    if not demo_mode:
        uploaded_image = st.file_uploader("Ортофотоплан (JPG/PNG)", type=["jpg", "jpeg", "png"])
        uploaded_table = st.file_uploader("Таблица деревьев (XLSX)", type=["xlsx"])
    gsd_m = st.number_input(
        "GSD изображения, м/пиксель", min_value=0.001, max_value=10.0,
        value=0.10, step=0.01, format="%.3f",
        help="Укажите фактический размер пикселя на местности. Исходные 0,10 м/пикс. — только значение по умолчанию.",
    )
    st.caption("X — столбец, Y — строка исходного изображения, начало координат в левом верхнем углу")

if demo_mode:
    img_file, tab_file = BASE_DIR / "forest.jpg", BASE_DIR / "trees.xlsx"
    if not img_file.exists() or not tab_file.exists():
        st.error("Для демонстрационного режима разместите forest.jpg и trees.xlsx рядом с app.py")
        st.stop()
    source_id = "demo:forest.jpg:trees.xlsx"
else:
    if uploaded_image is None or uploaded_table is None:
        st.info("Выберите снимок и Excel-таблицу либо включите демонстрационный режим.")
        st.stop()
    img_file, tab_file = uploaded_image, uploaded_table
    source_id = hashlib.sha256(uploaded_table.getvalue() + uploaded_image.getvalue()).hexdigest()[:12]

try:
    with Image.open(img_file) as opened:
        image = opened.convert("RGB")
    # PIL ограничивает недопустимо огромные изображения; графическая часть рассчитана на превью.
    raw_df = pd.read_excel(tab_file, engine="openpyxl")
    df, validation = clean_dataframe(raw_df, image.size)
except (ValueError, OSError, UnidentifiedImageError, ImportError) as exc:
    st.error(f"Не удалось загрузить входные файлы: {exc}")
    st.stop()

if validation["rejected_rows"]:
    st.warning(
        f"Исключено записей: {validation['rejected_rows']} из {validation['input_rows']}. "
        f"Пропуски: {validation['missing_values']}; некорректные размеры: "
        f"{validation['invalid_measurements']}; координаты вне изображения: "
        f"{validation['outside_image']}."
    )

with st.sidebar:
    if "Порода" in df.columns:
        st.success("Породный состав взят из загруженной таблицы")
        selected_species = None
    else:
        selected_species = st.selectbox("Порода деревьев (если нет столбца 'Порода')", list(SPECIES_DATA))
    st.caption(f"Действительных записей: {len(df)}; размер снимка: {image.width} × {image.height} пикс.")

df = calculate_additional_params(df, selected_species)
metrics = calculate_site_metrics(df, image.size, gsd_m, selected_species)

with st.sidebar:
    st.divider()
    st.header("🎯 Отбор деревьев")
    preset = st.radio("Режим", ["Все деревья", "Ручная настройка", "Заготовка древесины (пример)", "Молодняк (пример ухода)"], index=0)
    st.caption("Пресеты служат примером отбора. Они не подтверждают допустимость рубки или соответствие лесохозяйственным требованиям.")
    # Ключи виджетов зависят от текущего набора файлов: диапазоны не наследуются от другого проекта.
    numeric_columns = [c for c in df.select_dtypes(include="number").columns if c not in ("X", "Y", "ID")]
    selected_numeric = {}
    with st.expander("Диапазоны числовых показателей", expanded=(preset == "Ручная настройка")):
        for col in numeric_columns:
            vmin, vmax = float(df[col].min()), float(df[col].max())
            if not np.isfinite(vmin) or not np.isfinite(vmax):
                continue
            if abs(vmax - vmin) < 1e-10:
                st.caption(f"{col}: {vmin:.3f} (постоянная величина)")
                continue
            vals = st.slider(
                col, min_value=vmin, max_value=vmax, value=(vmin, vmax),
                key=f"s_{source_id}_{preset}_{col}",
            )
            selected_numeric[col] = vals
    selected_tov = st.multiselect("Класс товарности", TOVARNOST_OPTIONS, default=TOVARNOST_OPTIONS, key=f"t_{source_id}_{preset}")
    selected_size = st.multiselect("Категория крупности", SIZE_OPTIONS, default=SIZE_OPTIONS, key=f"z_{source_id}_{preset}")
    selected_bon = st.multiselect("Бонитет (условная оценка)", BONITET_OPTIONS, default=BONITET_OPTIONS, key=f"b_{source_id}_{preset}")
    selected_species_filter = (st.multiselect("Порода", sorted(df["Порода"].unique().tolist()), default=sorted(df["Порода"].unique().tolist()), key=f"p_{source_id}_{preset}") if "Порода" in df.columns else None)

filtered_df = apply_preset(df, preset)
for col, (lo, hi) in selected_numeric.items():
    filtered_df = filtered_df.loc[filtered_df[col].between(lo, hi)]
filtered_df = filtered_df.loc[
    filtered_df["Класс товарности"].isin(selected_tov) &
    filtered_df["Категория крупности"].isin(selected_size) &
    filtered_df["Бонитет"].isin(selected_bon)
]
if selected_species_filter is not None:
    filtered_df = filtered_df.loc[filtered_df["Порода"].isin(selected_species_filter)]

st.caption("Площадь и удельные показатели рассчитаны для всего прямоугольника изображения; без фактического GSD и границ участка они носят предварительный характер.")
a, b, c, d = st.columns(4)
a.metric("Деревьев в таблице", len(df))
b.metric("Отобрано", len(filtered_df))
c.metric("Доля отобранных деревьев", f"{len(filtered_df) / len(df) * 100:.1f}%")
d.metric("Охват снимка", f"{metrics['area_ha']:.3f} га")

st.markdown('<div class="section-title">🗺️ Деревья на снимке</div>', unsafe_allow_html=True)
with st.sidebar:
    color_field = st.selectbox("Цвет маркеров по показателю", numeric_columns, index=(numeric_columns.index("Высота, м") if "Высота, м" in numeric_columns else 0))
    marker_field = st.selectbox("Размер маркеров", ["Одинаковый"] + numeric_columns)

if filtered_df.empty:
    st.warning("Деревья не соответствуют текущим критериям. Измените фильтры.")
    st.image(image, use_container_width=True)
else:
    if marker_field == "Одинаковый":
        marker_sizes = np.full(len(filtered_df), 13)
    else:
        vals = filtered_df[marker_field].astype(float)
        extent = vals.max() - vals.min()
        marker_sizes = 10 + 20 * ((vals - vals.min()) / extent if extent > 1e-10 else 0.5)
    hover = []
    for pos, row in filtered_df.iterrows():
        tree_species = row.get("Порода", selected_species or "Не указана")
        hover.append(
            f"<b>Дерево #{escape(str(row['ID']))}</b><br>Порода: {escape(str(tree_species))}"
            f"<br>Высота: {row['Высота, м']:.2f} м"
            f"<br>Диаметр ствола: {row['Диаметр ствола, см']:.2f} см"
            f"<br>Площадь кроны: {row['Площадь кроны, м2']:.2f} м²"
            f"<br>Расчётный объём: {row['Объём_расчётный_м3']:.3f} м³"
            f"<br>Товарность*: {row['Класс товарности']}"
            f"<br>Бонитет*: {row['Бонитет']}"
        )
    fig = go.Figure()
    fig.add_layout_image(dict(
        source=image_as_data_uri(image), xref="x", yref="y", x=0, y=0,
        sizex=image.width, sizey=image.height, xanchor="left", yanchor="bottom",
        sizing="stretch", opacity=1, layer="below",
    ))
    fig.add_trace(go.Scatter(
        x=filtered_df["X"], y=image.height - filtered_df["Y"], mode="markers", name="Деревья",
        marker=dict(size=marker_sizes, color=filtered_df[color_field], colorscale="Viridis",
                    colorbar=dict(title=color_field), showscale=True, line=dict(color="white", width=0.7), opacity=0.85),
        text=hover, hoverinfo="text",
    ))
    fig.update_layout(
        height=660, margin=dict(l=0, r=0, t=4, b=0),
        xaxis=dict(range=[0, image.width], visible=False, constrain="domain"),
        yaxis=dict(range=[0, image.height], visible=False, scaleanchor="x", scaleratio=1),
        dragmode="zoom", hoverlabel=dict(bgcolor="white", font_size=12),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("* Расчётные ориентировочные классы: не заменяют лесотаксационные обследования.")

st.markdown('<div class="section-title">📊 Таксационная сводка</div>', unsafe_allow_html=True)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Сумма сечений", f"{metrics['basal_m2_total']:.2f} м²")
c2.metric("Сечение на 1 га", f"{metrics['basal_m2_ha']:.2f} м²/га")
c3.metric("Расчётный объём", f"{metrics['volume_m3_total']:.2f} м³")
c4.metric("Расчётный объём на 1 га", f"{metrics['volume_m3_ha']:.2f} м³/га")

with st.expander("Методические ограничения расчётов"):
    st.markdown(
        "Видовое число и класс товарности рассчитаны по упрощённым коэффициентам прототипа. "
        "Бонитет только по высоте без возраста **не является нормативным определением бонитета**. "
        "Индекс виталитета — относительная характеристика внутри набора, а не диагностическое заключение о состоянии дерева. "
        "Показатель доли отобранных деревьев не представляет собой комплексную оценку пригодности территории для рубки. "
        "Не учитываются ограничения ООПТ, водоохранные зоны, дорожная доступность и правовой статус участка."
    )

st.markdown('<div class="section-title">🌳 Реестр деревьев</div>', unsafe_allow_html=True)
search_term = st.text_input("Поиск по ID или породе", placeholder="Например, 12 или Сосна").strip()
visible_df = filtered_df
if search_term:
    id_hits = visible_df["ID"].astype(str).str.contains(search_term, case=False, regex=False, na=False)
    if "Порода" in visible_df.columns:
        id_hits = id_hits | visible_df["Порода"].astype(str).str.contains(search_term, case=False, regex=False, na=False)
    visible_df = visible_df.loc[id_hits]
rows_to_show = st.selectbox("Строк на странице", [10, 25, 50, 100, 500], index=1)
total_pages = max(1, (len(visible_df) + rows_to_show - 1) // rows_to_show)
page = st.number_input("Номер страницы", min_value=1, max_value=total_pages, value=1, step=1)
page_start = (page - 1) * rows_to_show
page_data = visible_df.iloc[page_start:page_start + rows_to_show]
st.dataframe(page_data, use_container_width=True, height=350)
st.caption(f"Страница {page}/{total_pages}; показано {len(page_data)} из {len(visible_df)} совпадений. Excel и CSV включают полную выборку.")
st.download_button("📥 Скачать выборку CSV (Excel/UTF-8)", filtered_df.to_csv(index=False, sep=";").encode("utf-8-sig"), file_name="lesanalitika_trees.csv", mime="text/csv")

st.markdown('<div class="section-title">📄 Отчёт по участку</div>', unsafe_allow_html=True)
rc1, rc2 = st.columns([2, 1])
with rc1:
    report_title = st.text_input("Название участка", value="Демонстрационный участок" if demo_mode else "Анализ лесного участка")
with rc2:
    report_date = st.date_input("Дата формирования", value=date.today())

try:
    report = build_excel_report(df, filtered_df, metrics, report_title, report_date, gsd_m, image.size, validation)
    st.download_button(
        "📥 Скачать Excel-отчёт", report, file_name=f"LesAnalitika_report_{report_date:%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
except (ValueError, ImportError, OSError) as exc:
    st.error(f"Не удалось сформировать Excel: {exc}")

st.divider()
st.caption("ЛесАналитика БПЛА · прототип на основе оригинального app.py · проект ФСИ № 107031 · улучшенная версия 1.1")
