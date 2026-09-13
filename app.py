import streamlit as st
import pandas as pd
import numpy as np
from PIL import Image
from datetime import datetime
import plotly.graph_objects as go  # Добавляем Plotly для интерактивности

# --- ФУНКЦИЯ ОЧИСТКИ ДАННЫХ ---
def clean_dataframe(df):
    """Принудительно преобразует ключевые колонки в числа"""
    numeric_columns = [
        'X', 'Y', 
        'Площадь кроны, м2', 'Диаметр кроны, м', 
        'Диаметр ствола, см', 'Высота, м', 'Объём ствола, м3'
    ]
    
    for col in numeric_columns:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(',', '.', regex=False)
            df[col] = df[col].str.strip()
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df = df.dropna(subset=['X', 'Y'])
    return df

# Настройка страницы
st.set_page_config(page_title="ЛесАналитика БПЛА", layout="wide")

# Заголовок
st.title("🌲 Модуль аналитического выявления древостоя")
st.markdown("---")

# --- СПРАВОЧНИК ПОРОД ---
SPECIES_DATA = {
    'Сосна': {
        'bonitet_table': {'I': 28, 'II': 24, 'III': 20, 'IV': 16, 'V': 12},
        'tovarnost': {'I класс': {'min_d': 24, 'min_h': 20}, 'II класс': {'min_d': 14, 'min_h': 15}, 'III класс': {'min_d': 0, 'min_h': 0}},
        'form_factor': 0.45, 'density_norm': 35
    },
    'Ель': {
        'bonitet_table': {'I': 30, 'II': 26, 'III': 22, 'IV': 18, 'V': 14},
        'tovarnost': {'I класс': {'min_d': 24, 'min_h': 20}, 'II класс': {'min_d': 14, 'min_h': 15}, 'III класс': {'min_d': 0, 'min_h': 0}},
        'form_factor': 0.42, 'density_norm': 38
    },
    'Берёза': {
        'bonitet_table': {'I': 26, 'II': 22, 'III': 18, 'IV': 14, 'V': 10},
        'tovarnost': {'I класс': {'min_d': 20, 'min_h': 18}, 'II класс': {'min_d': 12, 'min_h': 12}, 'III класс': {'min_d': 0, 'min_h': 0}},
        'form_factor': 0.40, 'density_norm': 30
    },
    'Осина': {
        'bonitet_table': {'I': 28, 'II': 24, 'III': 20, 'IV': 16, 'V': 12},
        'tovarnost': {'I класс': {'min_d': 22, 'min_h': 18}, 'II класс': {'min_d': 12, 'min_h': 12}, 'III класс': {'min_d': 0, 'min_h': 0}},
        'form_factor': 0.41, 'density_norm': 32
    },
    'Лиственница': {
        'bonitet_table': {'I': 30, 'II': 26, 'III': 22, 'IV': 18, 'V': 14},
        'tovarnost': {'I класс': {'min_d': 24, 'min_h': 20}, 'II класс': {'min_d': 14, 'min_h': 15}, 'III класс': {'min_d': 0, 'min_h': 0}},
        'form_factor': 0.44, 'density_norm': 34
    }
}

# --- ФУНКЦИИ РАСЧЁТА ---
def calculate_bonitet(height, species):
    bonitet_table = SPECIES_DATA[species]['bonitet_table']
    for bonitet_class, min_height in sorted(bonitet_table.items(), key=lambda x: x[1], reverse=True):
        if height >= min_height:
            return bonitet_class
    return 'V'

def calculate_tovarnost(diameter, height, species):
    tovarn_data = SPECIES_DATA[species]['tovarnost']
    for cls, params in tovarn_data.items():
        if diameter >= params['min_d'] and height >= params['min_h']:
            return cls
    return 'III класс'

def calculate_additional_params(df, species=None):
    df_calc = df.copy()
    has_species_column = 'Порода' in df_calc.columns
    
    # 1. Площадь поперечного сечения ствола (g), м²
    df_calc['g_сечения_м2'] = np.pi * (df_calc['Диаметр ствола, см'] / 100 / 2) ** 2
    
    # 2. Видовое число (f)
    def get_form_factor(row):
        if has_species_column and row['Порода'] in SPECIES_DATA:
            return SPECIES_DATA[row['Порода']]['form_factor']
        elif species and species in SPECIES_DATA:
            return SPECIES_DATA[species]['form_factor']
        return 0.45
    
    df_calc['Видовое число'] = df_calc.apply(get_form_factor, axis=1)
    df_calc['Объём_расчётный_м3'] = df_calc['g_сечения_м2'] * df_calc['Высота, м'] * df_calc['Видовое число']
    
    # 3. H/D ratio
    df_calc['H/D ratio'] = df_calc['Высота, м'] / (df_calc['Диаметр ствола, см'] / 100)
    
    # 4. Класс товарности
    def get_tovarnost(row):
        sp = row['Порода'] if has_species_column else species
        if sp and sp in SPECIES_DATA:
            tovarn_data = SPECIES_DATA[sp]['tovarnost']
            for cls, params in tovarn_data.items():
                if row['Диаметр ствола, см'] >= params['min_d'] and row['Высота, м'] >= params['min_h']:
                    return cls
        return 'III класс'
    df_calc['Класс товарности'] = df_calc.apply(get_tovarnost, axis=1)
    
    # 5. Категория крупности
    def get_size_category(d):
        if d < 8: return 'Мелкомер'
        elif d < 14: return 'Среднемер'
        elif d < 26: return 'Крупномер'
        else: return 'Очень крупный'
    df_calc['Категория крупности'] = df_calc['Диаметр ствола, см'].apply(get_size_category)
    
    # 6. Бонитет
    def get_bonitet(row):
        sp = row['Порода'] if has_species_column else species
        if sp and sp in SPECIES_DATA:
            bonitet_table = SPECIES_DATA[sp]['bonitet_table']
            for bonitet_class, min_height in sorted(bonitet_table.items(), key=lambda x: x[1], reverse=True):
                if row['Высота, м'] >= min_height:
                    return bonitet_class
        return 'V'
    df_calc['Бонитет'] = df_calc.apply(get_bonitet, axis=1)
    
    # 7. Индекс виталитета
    h_norm = (df_calc['Высота, м'] - df_calc['Высота, м'].min()) / (df_calc['Высота, м'].max() - df_calc['Высота, м'].min() + 1e-5)
    d_norm = (df_calc['Диаметр ствола, см'] - df_calc['Диаметр ствола, см'].min()) / (df_calc['Диаметр ствола, см'].max() - df_calc['Диаметр ствола, см'].min() + 1e-5)
    crown_norm = (df_calc['Площадь кроны, м2'] - df_calc['Площадь кроны, м2'].min()) / (df_calc['Площадь кроны, м2'].max() - df_calc['Площадь кроны, м2'].min() + 1e-5)
    df_calc['Индекс виталитета'] = (h_norm * 30 + d_norm * 40 + crown_norm * 30).round(1)
    
    # 8. Полнота и запас
    df_calc['Полнота_вклад'] = df_calc['g_сечения_м2']
    df_calc['Запас_м3_га'] = df_calc['Объём_расчётный_м3']
    
    return df_calc

# --- ЗАГРУЗКА ДАННЫХ ---
st.sidebar.header("📁 Загрузка данных")
uploaded_image = st.sidebar.file_uploader("Загрузите ортофотоплан (JPG, PNG)", type=["jpg", "jpeg", "png"])
uploaded_xlsx = st.sidebar.file_uploader("Загрузите таблицу с данными (XLSX)", type=["xlsx"])

demo_mode = st.sidebar.checkbox("Использовать демо-данные", value=False)

if demo_mode:
    try:
        image = Image.open("forest.jpg")
        df = pd.read_excel("trees.xlsx")
        df = clean_dataframe(df)
        st.sidebar.success("✅ Загружены демо-данные")
    except:
        st.error("Демо-файлы не найдены.")
        st.stop()
else:
    if uploaded_image is None or uploaded_xlsx is None:
        st.info("👆 Пожалуйста, загрузите ортофотоплан и таблицу с данными слева, или включите демо-режим")
        st.stop()
    try:
        image = Image.open(uploaded_image)
        df = pd.read_excel(uploaded_xlsx)
        df = clean_dataframe(df)
        st.sidebar.success("✅ Файлы успешно загружены!")
    except Exception as e:
        st.error(f"Ошибка при чтении файлов: {e}")
        st.stop()

# Проверка колонок
required_cols = ['X', 'Y', 'Площадь кроны, м2', 'Диаметр кроны, м', 'Диаметр ствола, см', 'Высота, м', 'Объём ствола, м3']
missing_cols = [col for col in required_cols if col not in df.columns]
if missing_cols:
    st.error(f"❌ Ошибка: В таблице отсутствуют колонки: {', '.join(missing_cols)}")
    st.stop()

# Генерация ID для интерактивности, если его нет
if 'ID' not in df.columns:
    df['ID'] = range(1, len(df) + 1)

has_species_column = 'Порода' in df.columns
species = None

if not has_species_column:
    st.sidebar.markdown("---")
    st.sidebar.header("🌳 Выбор породы")
    species = st.sidebar.selectbox("Выберите породу деревьев:", list(SPECIES_DATA.keys()), index=0)
    st.sidebar.info("ℹ️ В таблице нет колонки 'Порода'. Используется выбранная порода для всех деревьев.")
else:
    st.sidebar.success("✅ В таблице обнаружена колонка 'Порода'.")
    species_counts = df['Порода'].value_counts()
    st.sidebar.markdown("**📊 Распределение пород:**")
    for sp, count in species_counts.items():
        st.sidebar.write(f"• {sp}: **{count}** дер.")

# Расчёт параметров
df = calculate_additional_params(df, species)

# Агрегированные показатели
x_range = df['X'].max() - df['X'].min()
y_range = df['Y'].max() - df['Y'].min()
pixel_to_meter = 0.1
area_m2 = (x_range * pixel_to_meter) * (y_range * pixel_to_meter)
area_ha = area_m2 / 10000

total_g = df['g_сечения_м2'].sum()
density_per_ha = total_g / area_ha if area_ha > 0 else 0
# Берем норматив первой попавшейся породы или выбранной, если их несколько
ref_species = df['Порода'].iloc[0] if has_species_column else species
density_norm = SPECIES_DATA.get(ref_species, SPECIES_DATA['Сосنا'])['density_norm']
density_relative = (density_per_ha / density_norm * 100) if density_norm > 0 else 0

total_volume = df['Объём_расчётный_м3'].sum()
volume_per_ha = total_volume / area_ha if area_ha > 0 else 0

numeric_cols = [col for col in df.select_dtypes(include=['number']).columns if col not in ['X', 'Y', 'ID']]

# --- ФИЛЬТРАЦИЯ ---
st.sidebar.markdown("---")
st.sidebar.header("⚙️ Параметры фильтрации")

color_col = st.sidebar.selectbox("🎨 Параметр для цвета:", numeric_cols, index=0)
size_col = st.sidebar.selectbox("📏 Параметр для размера:", ["Нет"] + numeric_cols, index=0)

st.sidebar.markdown("**📊 Пороговые значения:**")
filters = {}
for col in numeric_cols:
    min_val, max_val = float(df[col].min()), float(df[col].max())
    if min_val == max_val: max_val = min_val + 1
    min_thresh, max_thresh = st.sidebar.slider(f"{col}:", min_value=min_val, max_value=max_val, value=(min_val, max_val), step=(max_val - min_val) / 100 if (max_val - min_val) > 0 else 0.1)
    filters[col] = (min_thresh, max_thresh)

tovarnost_options = st.sidebar.multiselect("🏷️ Класс товарности:", ['I класс', 'II класс', 'III класс'], default=['I класс', 'II класс', 'III класс'])
size_options = st.sidebar.multiselect("📦 Категория крупности:", ['Мелкомер', 'Среднемер', 'Крупномер', 'Очень крупный'], default=['Мелкомер', 'Среднемер', 'Крупномер', 'Очень крупный'])
bonitet_options = st.sidebar.multiselect("🌱 Бонитет:", ['I', 'II', 'III', 'IV', 'V'], default=['I', 'II', 'III', 'IV', 'V'])

filtered_df = df.copy()
for col, (min_t, max_t) in filters.items():
    filtered_df = filtered_df[(filtered_df[col] >= min_t) & (filtered_df[col] <= max_t)]
filtered_df = filtered_df[filtered_df['Класс товарности'].isin(tovarnost_options)]
filtered_df = filtered_df[filtered_df['Категория крупности'].isin(size_options)]
filtered_df = filtered_df[filtered_df['Бонитет'].isin(bonitet_options)]

# --- ИНФОРМАЦИЯ О ФАЙЛАХ ---
if not demo_mode:
    st.sidebar.markdown("---")
    st.sidebar.markdown("**📊 Информация:**")
    st.sidebar.write(f"Изображение: {uploaded_image.name}")
    st.sidebar.write(f"Таблица: {uploaded_xlsx.name}")
    st.sidebar.write(f"Записей: {len(df)}")

# ==========================================
# 🌟 ИНТЕРАКТИВНАЯ ВИЗУАЛИЗАЦИЯ (PLOTLY) 🌟
# ==========================================
col1, col2 = st.columns([3, 1])

with col1:
    st.subheader("🗺️ Интерактивная карта выделенных территорий")
    
    if not filtered_df.empty:
        fig = go.Figure()
        
        # 1. Добавляем фоновое изображение (ортофотоплан)
        fig.add_layout_image(
            dict(
                source=image,
                xref="x", yref="y",
                x=0, y=image.height,  # y=image.height, чтобы перевернуть ось Y как в картинке
                sizex=image.width, sizey=image.height,
                sizing="stretch", opacity=1, layer="below"
            )
        )
        
        # 2. Подготовка данных для всплывающих подсказок (customdata)
        # Если колонки 'Порода' нет, подставляем выбранную в сайдбаре
        species_display = filtered_df['Порода'] if 'Порода' in filtered_df.columns else pd.Series([species] * len(filtered_df))
        
        custom_data = np.column_stack((
            filtered_df['ID'],
            species_display,
            filtered_df['Высота, м'],
            filtered_df['Диаметр ствола, см'],
            filtered_df['Диаметр кроны, м'],
            filtered_df['Площадь кроны, м2'],
            filtered_df['Объём ствола, м3'],
            filtered_df['Объём_расчётный_м3'],
            filtered_df['Класс товарности'],
            filtered_df['Бонитет'],
            filtered_df['Категория крупности'],
            filtered_df['Индекс виталитета']
        ))
        
        # 3. Расчет размера точек
        if size_col != "Нет":
            sizes = (filtered_df[size_col] - filtered_df[size_col].min()) / (filtered_df[size_col].max() - filtered_df[size_col].min() + 1e-5) * 30 + 10
        else:
            sizes = [15] * len(filtered_df)
            
        # 4. Добавляем интерактивный scatter plot
        fig.add_trace(go.Scatter(
            x=filtered_df['X'],
            y=filtered_df['Y'],
            mode='markers',
            marker=dict(
                size=sizes,
                color=filtered_df[color_col],
                colorscale='RdYlGn',
                showscale=True,
                colorbar=dict(title=color_col, titleside='right'),
                line=dict(width=0.5, color='white'),
                opacity=0.85
            ),
            customdata=custom_data,
            hovertemplate=(
                "<b>🌲 Дерево ID: %{customdata[0]}</b><br>" +
                "Порода: %{customdata[1]}<br>" +
                "Высота: %{customdata[2]:.1f} м<br>" +
                "Диаметр ствола: %{customdata[3]:.1f} см<br>" +
                "Диаметр кроны: %{customdata[4]:.1f} м<br>" +
                "Площадь кроны: %{customdata[5]:.2f} м²<br>" +
                "Объём (исх.): %{customdata[6]:.3f} м³<br>" +
                "Объём (расч.): %{customdata[7]:.3f} м³<br>" +
                "Товарность: %{customdata[8]}<br>" +
                "Бонитет: %{customdata[9]}<br>" +
                "Крупность: %{customdata[10]}<br>" +
                "Виталитет: %{customdata[11]:.1f}<br>" +
                "<extra></extra>" # Убирает стандартную вторую панель подписи
            )
        ))
        
        # 5. Настройка осей и макета
        fig.update_layout(
            xaxis=dict(range=[0, image.width], showgrid=False, zeroline=False, visible=False),
            yaxis=dict(range=[image.height, 0], showgrid=False, zeroline=False, visible=False), # Инверсия Y
            margin=dict(l=0, r=0, t=40, b=0),
            height=700,
            hoverlabel=dict(bgcolor="white", font_size=12, font_family="Arial", bordercolor="#333")
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
    else:
        st.warning("Деревья не найдены. Измените параметры фильтрации.")
        st.image(image, caption="Ортофотоплан участка")

with col2:
    st.subheader("📈 Сводная аналитика")
    
    if has_species_column:
        st.metric("🌳 Породный состав", f"{len(df['Порода'].unique())} пород")
    else:
        st.metric("🌳 Пороada", species)
    
    st.metric("Всего деревьев", len(df))
    st.metric("🎯 Отобрано", len(filtered_df))
    
    suitability = (len(filtered_df) / len(df) * 100) if len(df) > 0 else 0
    st.metric("Индекс пригодности", f"{suitability:.1f}%")
    
    st.markdown("---")
    st.markdown("**📊 Показатели насаждения:**")
    st.metric("Площадь участка", f"{area_ha:.2f} га")
    st.metric("Полнота", f"{density_per_ha:.1f} м²/га")
    st.metric("Относит. полнота", f"{density_relative:.0f}%")
    st.metric("Запас древесины", f"{volume_per_ha:.1f} м³/га")
    
    st.markdown("---")
    st.markdown("**📊 Статистика по выборке:**")
    key_metrics = ['Высота, м', 'Диаметр ствола, см', 'Объём_расчётный_м3', 'Индекс виталитета']
    for col in key_metrics:
        if col in filtered_df.columns:
            st.write(f"Ср. {col}: **{filtered_df[col].mean():.2f}**")
    
    if not filtered_df.empty:
        st.markdown("---")
        st.markdown("**🏷️ По классам:**")
        for cls, count in filtered_df['Класс товарности'].value_counts().items():
            st.write(f"{cls}: **{count}**")
            
        st.markdown("**🌱 По бонитету:**")
        for bon, count in filtered_df['Бонитет'].value_counts().sort_index().items():
            st.write(f"Бонитет {bon}: **{count}**")
    
    if not filtered_df.empty:
        st.markdown("---")
        csv = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Скачать отфильтрованные данные (CSV)",
            data=csv,
            file_name=f'filtered_trees_{datetime.now().strftime("%Y%m%d")}.csv',
            mime='text/csv',
        )

# --- РАЗДЕЛ С ОТЧЁТОМ ---
st.markdown("---")
st.subheader("📄 Сформировать отчёт по участку")

col_report1, col_report2 = st.columns(2)

with col_report1:
    st.markdown("**Параметры отчёта:**")
    report_title = st.text_input("Название участка:", value=f"Таксация {species if species else 'Смешанный'}")
    report_date = st.date_input("Дата отчёта:", value=datetime.now())
    include_tables = st.checkbox("Включить полные данные", value=True)

with col_report2:
    st.markdown("**Содержание отчёта:**")
    include_summary = st.checkbox("Сводная аналитика", value=True)
    include_tovarnost = st.checkbox("Классы товарности", value=True)

if st.button("📥 Сформировать отчёт (Excel)", type="primary"):
    try:
        import xlsxwriter
        filename = f'отчет_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
        output = pd.ExcelWriter(filename, engine='xlsxwriter')
        
        if include_summary:
            summary_data = {
                'Параметр': ['Порода', 'Дата отчёта', 'Площадь участка, га', 'Всего деревьев', 'Отобрано по критериям', 'Полнота насаждения, м²/га', 'Относительная полнота, %', 'Запас древесины, м³/га', 'Средняя высота, м', 'Средний диаметр, см', 'Средний расч. объём, м³'],
                'Значение': [
                    (df['Порода'].mode()[0] if has_species_column else species), 
                    report_date.strftime('%d.%m.%Y'), f'{area_ha:.2f}', len(df), len(filtered_df),
                    f'{density_per_ha:.1f}', f'{density_relative:.0f}', f'{volume_per_ha:.1f}', 
                    f'{filtered_df["Высота, м"].mean():.1f}', f'{filtered_df["Диаметр ствола, см"].mean():.1f}',
                    f'{filtered_df["Объём_расчётный_м3"].mean():.3f}'
                ]
            }
            pd.DataFrame(summary_data).to_excel(output, sheet_name='Сводная информация', index=False)
        
        if include_tovarnost and not filtered_df.empty:
            tovarn_data = filtered_df['Класс товарности'].value_counts().reset_index()
            tovarn_data.columns = ['Класс товарности', 'Количество']
            tovarn_data.to_excel(output, sheet_name='Классы товарности', index=False)
            
            bonitet_data = filtered_df['Бонитет'].value_counts().sort_index().reset_index()
            bonitet_data.columns = ['Бонитет', 'Количество']
            bonitet_data.to_excel(output, sheet_name='Бонитет', index=False)
        
        if include_tables:
            filtered_df.to_excel(output, sheet_name='Полные данные', index=False)
        
        output.close()
        
        st.success("✅ Отчёт сформирован! Скачайте файл ниже:")
        with open(filename, 'rb') as f:
            st.download_button(
                label="📥 Скачать отчёт (Excel)",
                data=f,
                file_name=filename,
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
    except ImportError:
        st.error("Для создания Excel-отчётов установите библиотеку: `pip install xlsxwriter`")
