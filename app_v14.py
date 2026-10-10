import streamlit as st
import pandas as pd
import numpy as np
from PIL import Image
from datetime import datetime
import plotly.graph_objects as go
import base64
import io

# --- ФУНКЦИЯ ОЧИСТКИ ДАННЫХ ---
def clean_dataframe(df):
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

# --- ФУНКЦИЯ КОНВЕРТАЦИИ ИЗОБРАЖЕНИЯ В BASE64 ---
def get_image_base64(img):
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

# --- КАСТОМНЫЙ CSS ---
def local_css():
    st.markdown("""
        <style>
        .main-header {
            font-size: 2.5rem;
            font-weight: 600;
            color: #1e3a5f;
            margin-bottom: 1rem;
            text-align: center;
        }
        .sub-header {
            font-size: 1.3rem;
            font-weight: 500;
            color: #2c5282;
            margin: 1.5rem 0 1rem 0;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid #e2e8f0;
        }
        .stButton>button {
            background-color: #4299e1;
            color: white;
            border: none;
            padding: 0.75rem 2rem;
            border-radius: 8px;
            font-weight: 500;
            transition: all 0.3s ease;
        }
        .stButton>button:hover {
            background-color: #3182ce;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(66, 153, 225, 0.4);
        }
        hr {
            border: none;
            border-top: 1px solid #e2e8f0;
            margin: 2rem 0;
        }
        .stMarkdown {
            color: #4a5568;
            line-height: 1.6;
        }
        h3 {
            color: #2d3748;
            font-weight: 600;
            margin-top: 2rem;
        }
        @media (max-width: 768px) {
            .main-header {
                font-size: 2rem;
            }
        }
        </style>
    """, unsafe_allow_html=True)

local_css()

st.set_page_config(
    page_title="ЛесАналитика БПЛА",
    layout="wide",
    page_icon="🌲"
)

st.markdown('<h1 class="main-header">Система таксации лесов на основе данных БПЛА</h1>', unsafe_allow_html=True)
st.markdown('<p style="text-align: center; color: #718096; margin-bottom: 2rem;">Автоматизированный анализ древостоя и формирование отчетной документации</p>', unsafe_allow_html=True)
st.markdown("---")

# --- СПРАВОЧНИК ПОРОД ---
SPECIES_DATA = {
    'Сосна': {'bonitet_table': {'I': 28, 'II': 24, 'III': 20, 'IV': 16, 'V': 12}, 'tovarnost': {'I класс': {'min_d': 24, 'min_h': 20}, 'II класс': {'min_d': 14, 'min_h': 15}, 'III класс': {'min_d': 0, 'min_h': 0}}, 'form_factor': 0.45, 'density_norm': 35},
    'Ель': {'bonitet_table': {'I': 30, 'II': 26, 'III': 22, 'IV': 18, 'V': 14}, 'tovarnost': {'I класс': {'min_d': 24, 'min_h': 20}, 'II класс': {'min_d': 14, 'min_h': 15}, 'III класс': {'min_d': 0, 'min_h': 0}}, 'form_factor': 0.42, 'density_norm': 38},
    'Берёза': {'bonitet_table': {'I': 26, 'II': 22, 'III': 18, 'IV': 14, 'V': 10}, 'tovarnost': {'I класс': {'min_d': 20, 'min_h': 18}, 'II класс': {'min_d': 12, 'min_h': 12}, 'III класс': {'min_d': 0, 'min_h': 0}}, 'form_factor': 0.40, 'density_norm': 30},
    'Осина': {'bonitet_table': {'I': 28, 'II': 24, 'III': 20, 'IV': 16, 'V': 12}, 'tovarnost': {'I класс': {'min_d': 22, 'min_h': 18}, 'II класс': {'min_d': 12, 'min_h': 12}, 'III класс': {'min_d': 0, 'min_h': 0}}, 'form_factor': 0.41, 'density_norm': 32},
    'Лиственница': {'bonitet_table': {'I': 30, 'II': 26, 'III': 22, 'IV': 18, 'V': 14}, 'tovarnost': {'I класс': {'min_d': 24, 'min_h': 20}, 'II класс': {'min_d': 14, 'min_h': 15}, 'III класс': {'min_d': 0, 'min_h': 0}}, 'form_factor': 0.44, 'density_norm': 34}
}

def calculate_additional_params(df, species=None):
    df_calc = df.copy()
    has_species_column = 'Порода' in df_calc.columns
    df_calc['g_сечения_м2'] = np.pi * (df_calc['Диаметр ствола, см'] / 100 / 2) ** 2
    
    def get_form_factor(row):
        if has_species_column and row['Порода'] in SPECIES_DATA:
            return SPECIES_DATA[row['Порода']]['form_factor']
        elif species and species in SPECIES_DATA:
            return SPECIES_DATA[species]['form_factor']
        return 0.45
    
    df_calc['Видовое число'] = df_calc.apply(get_form_factor, axis=1)
    df_calc['Объём_расчётный_м3'] = df_calc['g_сечения_м2'] * df_calc['Высота, м'] * df_calc['Видовое число']
    df_calc['H/D ratio'] = df_calc['Высота, м'] / (df_calc['Диаметр ствола, см'] / 100)
    
    def get_tovarnost(row):
        sp = row['Порода'] if has_species_column else species
        if sp and sp in SPECIES_DATA:
            tovarn_data = SPECIES_DATA[sp]['tovarnost']
            for cls, params in tovarn_data.items():
                if row['Диаметр ствола, см'] >= params['min_d'] and row['Высота, м'] >= params['min_h']:
                    return cls
        return 'III класс'
    df_calc['Класс товарности'] = df_calc.apply(get_tovarnost, axis=1)
    
    def get_size_category(d):
        if d < 8: return 'Мелкомер'
        elif d < 14: return 'Среднемер'
        elif d < 26: return 'Крупномер'
        else: return 'Очень крупный'
    df_calc['Категория крупности'] = df_calc['Диаметр ствола, см'].apply(get_size_category)
    
    def get_bonitet(row):
        sp = row['Порода'] if has_species_column else species
        if sp and sp in SPECIES_DATA:
            bonitet_table = SPECIES_DATA[sp]['bonitet_table']
            for bonitet_class, min_height in sorted(bonitet_table.items(), key=lambda x: x[1], reverse=True):
                if row['Высота, м'] >= min_height:
                    return bonitet_class
        return 'V'
    df_calc['Бонитет'] = df_calc.apply(get_bonitet, axis=1)
    
    h_norm = (df_calc['Высота, м'] - df_calc['Высота, м'].min()) / (df_calc['Высота, м'].max() - df_calc['Высота, м'].min() + 1e-5)
    d_norm = (df_calc['Диаметр ствола, см'] - df_calc['Диаметр ствола, см'].min()) / (df_calc['Диаметр ствола, см'].max() - df_calc['Диаметр ствола, см'].min() + 1e-5)
    crown_norm = (df_calc['Площадь кроны, м2'] - df_calc['Площадь кроны, м2'].min()) / (df_calc['Площадь кроны, м2'].max() - df_calc['Площадь кроны, м2'].min() + 1e-5)
    df_calc['Индекс виталитета'] = (h_norm * 30 + d_norm * 40 + crown_norm * 30).round(1)
    df_calc['Полнота_вклад'] = df_calc['g_сечения_м2']
    df_calc['Запас_м3_га'] = df_calc['Объём_расчётный_м3']
    return df_calc

# --- ЗАГРУЗКА ДАННЫХ ---
with st.sidebar:
    st.markdown('<h3 style="color: #2d3748; margin-bottom: 1.5rem;">📁 Загрузка данных</h3>', unsafe_allow_html=True)
    
    uploaded_image = st.file_uploader("Ортофотоплан участка", type=["jpg", "jpeg", "png"], help="Загрузите аэрофотоснимок участка в формате JPG или PNG")
    uploaded_xlsx = st.file_uploader("Таблица с данными", type=["xlsx"], help="Таблица Excel с таксационными характеристиками деревьев")
    demo_mode = st.checkbox("Использовать демонстрационные данные", value=False)
    
    if demo_mode:
        try:
            image = Image.open("forest.jpg")
            df = pd.read_excel("trees.xlsx")
            df = clean_dataframe(df)
            st.success("✅ Демонстрационные данные загружены")
        except:
            st.error("❌ Демонстрационные файлы не найдены")
            st.stop()
    else:
        if uploaded_image is None or uploaded_xlsx is None:
            st.info(" Загрузите ортофотоплан и таблицу с данными")
            st.stop()
        try:
            image = Image.open(uploaded_image)
            if image.mode != 'RGB':
                image = image.convert('RGB')
            df = pd.read_excel(uploaded_xlsx)
            df = clean_dataframe(df)
            st.success("✅ Файлы успешно загружены")
        except Exception as e:
            st.error(f"❌ Ошибка при чтении файлов: {e}")
            st.stop()

# Проверка обязательных колонок
required_cols = ['X', 'Y', 'Площадь кроны, м2', 'Диаметр кроны, м', 'Диаметр ствола, см', 'Высота, м', 'Объём ствола, м3']
missing_cols = [col for col in required_cols if col not in df.columns]
if missing_cols:
    st.error(f"❌ В таблице отсутствуют колонки: {', '.join(missing_cols)}")
    st.stop()

if 'ID' not in df.columns:
    df['ID'] = range(1, len(df) + 1)

has_species_column = 'Порода' in df.columns
species = None

if not has_species_column:
    with st.sidebar:
        st.markdown('<h3 style="color: #2d3748; margin: 1.5rem 0 1rem 0;">🌳 Выбор породы</h3>', unsafe_allow_html=True)
        species = st.selectbox("Порода деревьев на участке:", list(SPECIES_DATA.keys()), index=0, help="Выберите преобладающую породу для расчета таксационных показателей")
else:
    st.sidebar.success("✅ В таблице указана порода деревьев")
    species_counts = df['Порода'].value_counts()
    st.sidebar.markdown("##### Распределение пород:")
    for sp, count in species_counts.items():
        st.sidebar.write(f"• {sp}: {count} дер.")

df = calculate_additional_params(df, species)

x_range = df['X'].max() - df['X'].min()
y_range = df['Y'].max() - df['Y'].min()
pixel_to_meter = 0.1
area_m2 = (x_range * pixel_to_meter) * (y_range * pixel_to_meter)
area_ha = area_m2 / 10000

total_g = df['g_сечения_м2'].sum()
density_per_ha = total_g / area_ha if area_ha > 0 else 0
ref_species = df['Порода'].iloc[0] if has_species_column else species
density_norm = SPECIES_DATA.get(ref_species, SPECIES_DATA['Сосна'])['density_norm']
density_relative = (density_per_ha / density_norm * 100) if density_norm > 0 else 0

total_volume = df['Объём_расчётный_м3'].sum()
volume_per_ha = total_volume / area_ha if area_ha > 0 else 0

numeric_cols = [col for col in df.select_dtypes(include=['number']).columns if col not in ['X', 'Y', 'ID']]

# =====================================================================
# 🎯 БЛОК ПРЕСЕТОВ И ФИЛЬТРАЦИИ С ИСПОЛЬЗОВАНИЕМ SESSION_STATE
# =====================================================================

# 1. Инициализация session_state (только при первом запуске)
if 'preset_mode' not in st.session_state:
    st.session_state.preset_mode = "Ручная настройка"

if 'filters' not in st.session_state:
    st.session_state.filters = {}
    for col in numeric_cols:
        min_val, max_val = float(df[col].min()), float(df[col].max())
        if min_val == max_val:
            max_val = min_val + 1
        st.session_state.filters[col] = (min_val, max_val)

if 'tovarnost_options' not in st.session_state:
    st.session_state.tovarnost_options = ['I класс', 'II класс', 'III класс']

if 'size_options' not in st.session_state:
    st.session_state.size_options = ['Мелкомер', 'Среднемер', 'Крупномер', 'Очень крупный']

if 'bonitet_options' not in st.session_state:
    st.session_state.bonitet_options = ['I', 'II', 'III', 'IV', 'V']

# 2. Функция применения пресета
def apply_preset(preset_name, df, numeric_cols):
    """Применяет пресет и обновляет session_state"""
    
    if preset_name == "Заготовка древесины (оптимум)":
        for col in numeric_cols:
            min_val, max_val = float(df[col].min()), float(df[col].max())
            if col == 'Высота, м':
                st.session_state.filters[col] = (20.0, max_val)
            elif col == 'Объём ствола, м3':
                st.session_state.filters[col] = (1.0, max_val)
            elif col == 'Объём_расчётный_м3':
                st.session_state.filters[col] = (1.0, max_val)
            elif col == 'Диаметр ствола, см':
                st.session_state.filters[col] = (14.0, max_val)
            else:
                st.session_state.filters[col] = (min_val, max_val)
        
        st.session_state.tovarnost_options = ['I класс', 'II класс']
        st.session_state.size_options = ['Крупномер', 'Очень крупный']
        st.session_state.bonitet_options = ['I', 'II', 'III']
        
    elif preset_name == "Молодняк (уход)":
        for col in numeric_cols:
            min_val, max_val = float(df[col].min()), float(df[col].max())
            if col == 'Высота, м':
                st.session_state.filters[col] = (5.0, 15.0)
            elif col == 'Диаметр ствола, см':
                st.session_state.filters[col] = (8.0, 20.0)
            else:
                st.session_state.filters[col] = (min_val, max_val)
        
        st.session_state.tovarnost_options = ['III класс']
        st.session_state.size_options = ['Мелкомер', 'Среднемер']
        st.session_state.bonitet_options = ['I', 'II', 'III', 'IV', 'V']
        
    elif preset_name == "Все деревья":
        for col in numeric_cols:
            min_val, max_val = float(df[col].min()), float(df[col].max())
            st.session_state.filters[col] = (min_val, max_val)
        
        st.session_state.tovarnost_options = ['I класс', 'II класс', 'III класс']
        st.session_state.size_options = ['Мелкомер', 'Среднемер', 'Крупномер', 'Очень крупный']
        st.session_state.bonitet_options = ['I', 'II', 'III', 'IV', 'V']

# 3. Виджет выбора пресета (в sidebar)
with st.sidebar:
    st.markdown("---")
    st.markdown("### 🎯 Пресеты фильтрации")
    
    preset_mode = st.radio(
        "Выберите режим фильтрации:",
        ["Ручная настройка", "Заготовка древесины (оптимум)", "Молодняк (уход)", "Все деревья"],
        index=0,
        key="preset_radio"
    )
    
    # Если пресет изменился — применяем его
    if preset_mode != st.session_state.preset_mode:
        st.session_state.preset_mode = preset_mode
        apply_preset(preset_mode, df, numeric_cols)
        st.rerun()  # Перезапускаем для обновления виджетов
    
    # Показываем информацию о текущем пресете
    if preset_mode == "Заготовка древесины (оптимум)":
        st.success("✅ Применены оптимальные параметры для заготовки древесины")
        st.info("📋 Критерии:\n• Высота ≥ 20 м\n• Объем ≥ 1 м³\n• Диаметр ≥ 14 см\n• I-II класс товарности\n• I-III бонитет")
    elif preset_mode == "Молодняк (уход)":
        st.success("✅ Применены параметры для ухода за молодняком")
        st.info("📋 Критерии:\n• Высота 5-15 м\n• Диаметр 8-20 см\n• III класс товарности")
    elif preset_mode == "Все деревья":
        st.success("✅ Отображаются все деревья")

# 4. Виджеты фильтрации (читают и записывают в session_state)
with st.sidebar:
    st.markdown("---")
    st.markdown('<h3 style="color: #2d3748;">⚙️ Настройки отображения</h3>', unsafe_allow_html=True)
    
    color_col = st.selectbox("Цветовая индикация:", numeric_cols, index=0, help="Параметр для цветового отображения деревьев на карте")
    size_col = st.selectbox("Размер маркеров:", ["Нет"] + numeric_cols, index=0, help="Параметр для определения размера точек")
    
    st.markdown("##### Пороговые значения:")
    
    # Слайдеры с привязкой к session_state
    for col in numeric_cols:
        min_val, max_val = float(df[col].min()), float(df[col].max())
        if min_val == max_val:
            max_val = min_val + 1
        
        # Получаем текущее значение из session_state
        current_value = st.session_state.filters.get(col, (min_val, max_val))
        
        # Ограничиваем значение допустимым диапазоном
        current_min = max(min(current_value[0], current_value[1]), min_val)
        current_max = min(max(current_value[0], current_value[1]), max_val)
        if current_min > current_max:
            current_min = current_max
        
        new_value = st.slider(
            f"{col}:",
            min_value=min_val,
            max_value=max_val,
            value=(current_min, current_max),
            step=(max_val - min_val) / 100 if (max_val - min_val) > 0 else 0.1,
            key=f"slider_{col}"
        )
        
        # Сохраняем в session_state
        st.session_state.filters[col] = new_value
    
    # Мультиселекты с привязкой к session_state
    st.markdown("**🏷️ Класс товарности:**")
    st.session_state.tovarnost_options = st.multiselect(
        "Выберите классы:",
        ['I класс', 'II класс', 'III класс'],
        default=st.session_state.tovarnost_options,
        key="tovarnost_select"
    )
    
    st.markdown("**📦 Категория крупности:**")
    st.session_state.size_options = st.multiselect(
        "Выберите категории:",
        ['Мелкомер', 'Среднемер', 'Крупномер', 'Очень крупный'],
        default=st.session_state.size_options,
        key="size_select"
    )
    
    st.markdown("** Бонитет:**")
    st.session_state.bonitet_options = st.multiselect(
        "Выберите бонитет:",
        ['I', 'II', 'III', 'IV', 'V'],
        default=st.session_state.bonitet_options,
        key="bonitet_select"
    )

# 5. ФИЛЬТРАЦИЯ ДАННЫХ (использует session_state)
filtered_df = df.copy()

for col, (min_t, max_t) in st.session_state.filters.items():
    if col in filtered_df.columns:
        filtered_df = filtered_df[(filtered_df[col] >= min_t) & (filtered_df[col] <= max_t)]

filtered_df = filtered_df[filtered_df['Класс товарности'].isin(st.session_state.tovarnost_options)]
filtered_df = filtered_df[filtered_df['Категория крупности'].isin(st.session_state.size_options)]
filtered_df = filtered_df[filtered_df['Бонитет'].isin(st.session_state.bonitet_options)]

if not demo_mode:
    with st.sidebar:
        st.markdown("---")
        st.markdown("##### Информация о файлах:")
        st.write(f"📄 {uploaded_image.name}")
        st.write(f"📊 {uploaded_xlsx.name}")
        st.write(f"📋 Записей: {len(df)}")

# =====================================================================
# ОСНОВНАЯ ВИЗУАЛИЗАЦИЯ
# =====================================================================
st.markdown('<h2 class="sub-header">🗺️ Интерактивная карта участка</h2>', unsafe_allow_html=True)

col1, col2 = st.columns([3, 1])

with col1:
    if not filtered_df.empty:
        fig = go.Figure()
        img_base64 = get_image_base64(image)
        
        fig.add_layout_image(
            dict(
                source=img_base64,
                xref="x",
                yref="y",
                x=0,
                y=0,
                sizex=image.width,
                sizey=image.height,
                xanchor="left",
                yanchor="bottom",
                sizing="stretch",
                opacity=1.0,
                layer="below"
            )
        )
        
        hover_texts = []
        for i, row in filtered_df.iterrows():
            tree_species = row.get('Порода', species if species else 'Не указана')
            tree_id = row.get('ID', i + 1)
            text = (
                f"<b>Дерево #{tree_id}</b><br>"
                f"Порода: {tree_species}<br>"
                f"Высота: {row['Высота, м']:.1f} м<br>"
                f"Диаметр ствола: {row['Диаметр ствола, см']:.1f} см<br>"
                f"Диаметр кроны: {row['Диаметр кроны, м']:.1f} м<br>"
                f"Площадь кроны: {row['Площадь кроны, м2']:.2f} м²<br>"
                f"Объём (исх.): {row['Объём ствола, м3']:.3f} м³<br>"
                f"Объём (расч.): {row['Объём_расчётный_м3']:.3f} м³<br>"
                f"Товарность: {row['Класс товарности']}<br>"
                f"Бонитет: {row['Бонитет']}<br>"
                f"Крупность: {row['Категория крупности']}<br>"
                f"Виталитет: {row['Индекс виталитета']:.1f}"
            )
            hover_texts.append(text)
        
        if size_col != "Нет":
            sizes = (filtered_df[size_col] - filtered_df[size_col].min()) / (filtered_df[size_col].max() - filtered_df[size_col].min() + 1e-5) * 30 + 10
        else:
            sizes = [15] * len(filtered_df)
        
        fig.add_trace(go.Scatter(
            x=filtered_df['X'],
            y=image.height - filtered_df['Y'],
            mode='markers',
            marker=dict(
                size=sizes,
                color=filtered_df[color_col],
                colorscale='RdYlGn',
                showscale=True,
                colorbar=dict(title=color_col),
                line=dict(width=1, color='white'),
                opacity=0.9
            ),
            text=hover_texts,
            hoverinfo='text',
            name='Деревья'
        ))
        
        fig.update_layout(
            xaxis=dict(range=[0, image.width], showgrid=False, zeroline=False, visible=False),
            yaxis=dict(range=[0, image.height], showgrid=False, zeroline=False, visible=False),
            margin=dict(l=0, r=0, t=40, b=0),
            height=700,
            hoverlabel=dict(bgcolor="white", font_size=12, font_family="Arial", bordercolor="#333")
        )
        
        st.plotly_chart(fig, use_container_width=True)
        st.info("💡 Наведите курсор на точку для просмотра характеристик дерева")
    else:
        st.warning("⚠️ Деревья не найдены. Измените параметры фильтрации.")
        st.image(image, caption="Ортофотоплан участка", use_container_width=True)

with col2:
    st.markdown('<h3 class="sub-header">📊 Результаты анализа</h3>', unsafe_allow_html=True)
    
    if has_species_column:
        st.metric("Породный состав", f"{len(df['Порода'].unique())} пород")
    else:
        st.metric("Порода", species)
    
    st.metric("Всего деревьев", len(df))
    st.metric("Отобрано по критериям", len(filtered_df))
    
    suitability = (len(filtered_df) / len(df) * 100) if len(df) > 0 else 0
    st.metric("Пригодность территории", f"{suitability:.1f}%")
    
    st.markdown("---")
    st.markdown("##### Таксационные показатели:")
    st.metric("Площадь участка", f"{area_ha:.2f} га")
    st.metric("Полнота насаждения", f"{density_per_ha:.1f} м²/га")
    st.metric("Относительная полнота", f"{density_relative:.0f}%")
    st.metric("Запас древесины", f"{volume_per_ha:.1f} м³/га")
    
    st.markdown("---")
    st.markdown("##### Статистика выборки:")
    key_metrics = ['Высота, м', 'Диаметр ствола, см', 'Объём_расчётный_м3', 'Индекс виталитета']
    for col in key_metrics:
        if col in filtered_df.columns:
            st.write(f"Среднее {col}: **{filtered_df[col].mean():.2f}**")
    
    if not filtered_df.empty:
        st.markdown("---")
        st.markdown("##### Распределение по классам:")
        for cls, count in filtered_df['Класс товарности'].value_counts().items():
            st.write(f"{cls}: **{count}**")
        
        st.markdown("##### Распределение по бонитету:")
        for bon, count in filtered_df['Бонитет'].value_counts().sort_index().items():
            st.write(f"Бонитет {bon}: **{count}**")
    
    if not filtered_df.empty:
        st.markdown("---")
        csv = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Скачать данные (CSV)",
            data=csv,
            file_name=f'filtered_trees_{datetime.now().strftime("%Y%m%d")}.csv',
            mime='text/csv',
        )

# Раздел отчётности
st.markdown("---")
st.markdown('<h2 class="sub-header">📄 Формирование отчётной документации</h2>', unsafe_allow_html=True)

col_report1, col_report2 = st.columns(2)

with col_report1:
    st.markdown("##### Параметры отчёта:")
    report_title = st.text_input("Наименование участка:", value=f"Таксация {species if species else 'Смешанный'}")
    report_date = st.date_input("Дата составления:", value=datetime.now())
    include_tables = st.checkbox("Включить полные данные", value=True)

with col_report2:
    st.markdown("##### Содержание отчёта:")
    include_summary = st.checkbox("Сводная информация", value=True)
    include_tovarnost = st.checkbox("Классы товарности", value=True)

if st.button(" Сформировать отчёт Excel", type="primary", use_container_width=True):
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
        
        st.success("✅ Отчёт успешно сформирован!")
        with open(filename, 'rb') as f:
            st.download_button(
                label="📥 Скачать отчёт Excel",
                data=f,
                file_name=filename,
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                use_container_width=True
            )
    except ImportError:
        st.error("❌ Установите библиотеку: `pip install xlsxwriter`")

# Footer
st.markdown("---")
st.markdown('<p style="text-align: center; color: #718096; font-size: 0.9rem;">© 2024 Система таксации лесов на основе данных БПЛА</p>', unsafe_allow_html=True)
