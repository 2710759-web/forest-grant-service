import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from PIL import Image
import numpy as np
from datetime import datetime

# Настройка страницы
st.set_page_config(page_title="ЛесАналитика БПЛА", layout="wide")

# Заголовок
st.title("🌲 Модуль аналитического выявления древостоя")
st.markdown("---")

# --- СПРАВОЧНИК ПОРОД ---
SPECIES_DATA = {
    'Сосна': {
        'bonitet_table': {
            'I': 28, 'II': 24, 'III': 20, 'IV': 16, 'V': 12
        },
        'tovarnost': {
            'I класс': {'min_d': 24, 'min_h': 20},
            'II класс': {'min_d': 14, 'min_h': 15},
            'III класс': {'min_d': 0, 'min_h': 0}
        },
        'form_factor': 0.45,  # Среднее видовое число
        'density_norm': 35  # Нормативная полнота (м²/га)
    },
    'Ель': {
        'bonitet_table': {
            'I': 30, 'II': 26, 'III': 22, 'IV': 18, 'V': 14
        },
        'tovarnost': {
            'I класс': {'min_d': 24, 'min_h': 20},
            'II класс': {'min_d': 14, 'min_h': 15},
            'III класс': {'min_d': 0, 'min_h': 0}
        },
        'form_factor': 0.42,
        'density_norm': 38
    },
    'Берёза': {
        'bonitet_table': {
            'I': 26, 'II': 22, 'III': 18, 'IV': 14, 'V': 10
        },
        'tovarnost': {
            'I класс': {'min_d': 20, 'min_h': 18},
            'II класс': {'min_d': 12, 'min_h': 12},
            'III класс': {'min_d': 0, 'min_h': 0}
        },
        'form_factor': 0.40,
        'density_norm': 30
    },
    'Осина': {
        'bonitet_table': {
            'I': 28, 'II': 24, 'III': 20, 'IV': 16, 'V': 12
        },
        'tovarnost': {
            'I класс': {'min_d': 22, 'min_h': 18},
            'II класс': {'min_d': 12, 'min_h': 12},
            'III класс': {'min_d': 0, 'min_h': 0}
        },
        'form_factor': 0.41,
        'density_norm': 32
    },
    'Лиственница': {
        'bonitet_table': {
            'I': 30, 'II': 26, 'III': 22, 'IV': 18, 'V': 14
        },
        'tovarnost': {
            'I класс': {'min_d': 24, 'min_h': 20},
            'II класс': {'min_d': 14, 'min_h': 15},
            'III класс': {'min_d': 0, 'min_h': 0}
        },
        'form_factor': 0.44,
        'density_norm': 34
    }
}

# --- ФУНКЦИЯ РАСЧЁТА БОНИТЕТА ---
def calculate_bonitet(height, species):
    """Рассчитывает бонитет по высоте и породе"""
    bonitet_table = SPECIES_DATA[species]['bonitet_table']
    for bonitet_class, min_height in sorted(bonitet_table.items(), key=lambda x: x[1], reverse=True):
        if height >= min_height:
            return bonitet_class
    return 'V'

# --- ФУНКЦИЯ РАСЧЁТА КЛАССА ТОВАРНОСТИ ---
def calculate_tovarnost(diameter, height, species):
    """Рассчитывает класс товарности по диаметру, высоте и породе"""
    tovarn_data = SPECIES_DATA[species]['tovarnost']
    for cls, params in tovarn_data.items():
        if diameter >= params['min_d'] and height >= params['min_h']:
            return cls
    return 'III класс'

# --- ФУНКЦИЯ РАСЧЁТА ОБЪЁМА СТВОЛА ---
def calculate_volume(diameter_cm, height_m, species, method='formula'):
    """
    Рассчитывает объём ствола
    method: 'formula' - по формуле, 'tables' - по таблицам (упрощённо)
    """
    d_m = diameter_cm / 100  # Перевод в метры
    g = np.pi * (d_m / 2) ** 2  # Площадь сечения
    
    if method == 'formula':
        # V = g * h * f (видовое число)
        f = SPECIES_DATA[species]['form_factor']
        return g * height_m * f
    else:
        # Упрощённая табличная формула (для демонстрации)
        # V ≈ 0.00005 * d^2 * h (где d в см, h в м)
        return 0.00005 * (diameter_cm ** 2) * height_m

# --- ФУНКЦИЯ РАСЧЁТА ДОПОЛНИТЕЛЬНЫХ ПАРАМЕТРОВ ---
def calculate_additional_params(df, species):
    """Рассчитывает все дополнительные лесоводственные показатели"""
    df_calc = df.copy()
    
    # 1. Площадь поперечного сечения ствола (g), м²
    df_calc['g_сечения_м2'] = np.pi * (df_calc['Диаметр ствола, см'] / 100 / 2) ** 2
    
    # 2. Видовое число (f)
    df_calc['Видовое число'] = df_calc['Объём ствола, м3'] / (df_calc['g_сечения_м2'] * df_calc['Высота, м'])
    df_calc['Видовое число'] = df_calc['Видовое число'].clip(0.2, 0.7)
    
    # 3. Рассчитанный объём ствола (по формуле)
    df_calc['Объём_расчётный_м3'] = df_calc.apply(
        lambda row: calculate_volume(row['Диаметр ствола, см'], row['Высота, м'], species, 'formula'),
        axis=1
    )
    
    # 4. Соотношение высоты к диаметру (H/D)
    df_calc['H/D ratio'] = df_calc['Высота, м'] / (df_calc['Диаметр ствола, см'] / 100)
    
    # 5. Класс товарности (породозависимый)
    df_calc['Класс товарности'] = df_calc.apply(
        lambda row: calculate_tovarnost(row['Диаметр ствола, см'], row['Высота, м'], species),
        axis=1
    )
    
    # 6. Категория крупности
    def get_size_category(d):
        if d < 8:
            return 'Мелкомер'
        elif d < 14:
            return 'Среднемер'
        elif d < 26:
            return 'Крупномер'
        else:
            return 'Очень крупный'
    df_calc['Категория крупности'] = df_calc['Диаметр ствола, см'].apply(get_size_category)
    
    # 7. Бонитет (породозависимый)
    df_calc['Бонитет'] = df_calc['Высота, м'].apply(lambda h: calculate_bonitet(h, species))
    
    # 8. Индекс виталитета
    h_norm = (df_calc['Высота, м'] - df_calc['Высота, м'].min()) / (df_calc['Высота, м'].max() - df_calc['Высота, м'].min() + 1e-5)
    d_norm = (df_calc['Диаметр ствола, см'] - df_calc['Диаметр ствола, см'].min()) / (df_calc['Диаметр ствола, см'].max() - df_calc['Диаметр ствола, см'].min() + 1e-5)
    crown_norm = (df_calc['Площадь кроны, м2'] - df_calc['Площадь кроны, м2'].min()) / (df_calc['Площадь кроны, м2'].max() - df_calc['Площадь кроны, м2'].min() + 1e-5)
    df_calc['Индекс виталитета'] = (h_norm * 30 + d_norm * 40 + crown_norm * 30).round(1)
    
    # 9. Полнота насаждения (для каждого дерева - вклад в полноту)
    # Полнота = сумма g / площадь участка (упрощённо считаем на 1 га)
    df_calc['Полнота_вклад'] = df_calc['g_сечения_м2']
    
    # 10. Запас древесины (м³/га) - для каждого дерева
    # Запас = объём * количество деревьев на 1 га (упрощённо)
    df_calc['Запас_м3_га'] = df_calc['Объём_расчётный_м3']
    
    return df_calc

# --- БОКОВАЯ ПАНЕЛЬ С ЗАГРУЗКОЙ ФАЙЛОВ ---
st.sidebar.header("📁 Загрузка данных")

uploaded_image = st.sidebar.file_uploader(
    "Загрузите ортофотоплан (JPG, PNG)",
    type=["jpg", "jpeg", "png"]
)

uploaded_xlsx = st.sidebar.file_uploader(
    "Загрузите таблицу с данными (XLSX)",
    type=["xlsx"]
)

# Выбор породы
if uploaded_xlsx is not None:
    st.sidebar.markdown("---")
    st.sidebar.header("🌳 Выбор породы")
    species = st.sidebar.selectbox(
        "Выберите породу деревьев:",
        list(SPECIES_DATA.keys()),
        index=0
    )
else:
    species = 'Сосна'  # По умолчанию

# Демо-режим
demo_mode = st.sidebar.checkbox("Использовать демо-данные", value=False)

# --- ЗАГРУЗКА ДАННЫХ ---
if demo_mode:
    try:
        image = Image.open("forest.jpg")
        df = pd.read_excel("trees.xlsx")
        st.sidebar.success("✅ Загружены демо-данные")
    except:
        st.error("Демо-файлы не найдены. Пожалуйста, загрузите свои файлы.")
        st.stop()
else:
    if uploaded_image is None or uploaded_xlsx is None:
        st.info(" Пожалуйста, загрузите ортофотоплан и таблицу с данными слева, или включите демо-режим")
        st.stop()
    
    try:
        image = Image.open(uploaded_image)
        df = pd.read_excel(uploaded_xlsx)
        st.sidebar.success("✅ Файлы успешно загружены!")
    except Exception as e:
        st.error(f"Ошибка при чтении файлов: {e}")
        st.stop()

# Проверяем наличие обязательных колонок
required_cols = ['X', 'Y', 'Площадь кроны, м2', 'Диаметр кроны, м', 'Диаметр ствола, см', 'Высота, м', 'Объём ствола, м3']
missing_cols = [col for col in required_cols if col not in df.columns]
if missing_cols:
    st.error(f"❌ Ошибка: В таблице отсутствуют колонки: {', '.join(missing_cols)}")
    st.stop()

# --- РАСЧЁТ ДОПОЛНИТЕЛЬНЫХ ПАРАМЕТРОВ ---
df = calculate_additional_params(df, species)

# --- АГРЕГИРОВАННЫЕ ПОКАЗАТЕЛИ ПО УЧАСТКУ ---
# Площадь участка (упрощённо считаем по bounding box точек)
x_range = df['X'].max() - df['X'].min()
y_range = df['Y'].max() - df['Y'].min()
# Переводим пиксели в метры (упрощённо: 1 пиксель = 0.1 м, можно настроить)
pixel_to_meter = 0.1
area_m2 = (x_range * pixel_to_meter) * (y_range * pixel_to_meter)
area_ha = area_m2 / 10000  # В гектарах

# Полнота насаждения (сумма g на участок)
total_g = df['g_сечения_м2'].sum()
density_per_ha = total_g / area_ha if area_ha > 0 else 0
density_norm = SPECIES_DATA[species]['density_norm']
density_relative = (density_per_ha / density_norm * 100) if density_norm > 0 else 0

# Запас древесины на участок
total_volume = df['Объём_расчётный_м3'].sum()
volume_per_ha = total_volume / area_ha if area_ha > 0 else 0

# Находим все числовые колонки для фильтров
numeric_cols = [col for col in df.select_dtypes(include=['number']).columns if col not in ['X', 'Y']]

# --- БОКОВАЯ ПАНЕЛЬ С НАСТРОЙКАМИ ---
st.sidebar.markdown("---")
st.sidebar.header("️ Параметры фильтрации")

# Выбор параметра для цвета и размера точек
color_col = st.sidebar.selectbox("🎨 Параметр для цветовой индикации:", numeric_cols, index=0)
size_col = st.sidebar.selectbox("📏 Параметр для размера точек:", ["Нет"] + numeric_cols, index=0)

# Ползунки для пороговых значений
st.sidebar.markdown("**📊 Пороговые значения:**")
filters = {}
for col in numeric_cols:
    min_val = float(df[col].min())
    max_val = float(df[col].max())
    if min_val == max_val:
        max_val = min_val + 1
    
    min_thresh, max_thresh = st.sidebar.slider(
        f"{col}:",
        min_value=min_val,
        max_value=max_val,
        value=(min_val, max_val),
        step=(max_val - min_val) / 100 if (max_val - min_val) > 0 else 0.1
    )
    filters[col] = (min_thresh, max_thresh)

# Фильтры по категориальным параметрам
st.sidebar.markdown("**️ Класс товарности:**")
tovarnost_options = st.sidebar.multiselect(
    "Выберите классы:",
    ['I класс', 'II класс', 'III класс'],
    default=['I класс', 'II класс', 'III класс']
)

st.sidebar.markdown("**📦 Категория крупности:**")
size_options = st.sidebar.multiselect(
    "Выберите категории:",
    ['Мелкомер', 'Среднемер', 'Крупномер', 'Очень крупный'],
    default=['Мелкомер', 'Среднемер', 'Крупномер', 'Очень крупный']
)

st.sidebar.markdown("**🌱 Бонитет:**")
bonitet_options = st.sidebar.multiselect(
    "Выберите бонитет:",
    ['I', 'II', 'III', 'IV', 'V'],
    default=['I', 'II', 'III', 'IV', 'V']
)

# --- ФИЛЬТРАЦИЯ ДАННЫХ ---
filtered_df = df.copy()

for col, (min_t, max_t) in filters.items():
    filtered_df = filtered_df[(filtered_df[col] >= min_t) & (filtered_df[col] <= max_t)]

filtered_df = filtered_df[filtered_df['Класс товарности'].isin(tovarnost_options)]
filtered_df = filtered_df[filtered_df['Категория крупности'].isin(size_options)]
filtered_df = filtered_df[filtered_df['Бонитет'].isin(bonitet_options)]

# --- ИНФОРМАЦИЯ О ФАЙЛАХ ---
if not demo_mode:
    st.sidebar.markdown("---")
    st.sidebar.markdown("**📊 Информация о файлах:**")
    st.sidebar.write(f"Изображение: {uploaded_image.name}")
    st.sidebar.write(f"Таблица: {uploaded_xlsx.name}")
    st.sidebar.write(f"Порода: {species}")
    st.sidebar.write(f"Размер изображения: {image.width} × {image.height} px")
    st.sidebar.write(f"Записей в таблице: {len(df)}")

# --- ВИЗУАЛИЗАЦИЯ ---
col1, col2 = st.columns([3, 1])

with col1:
    st.subheader("️ Карта выделенных территорий")
    
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.imshow(image, extent=[0, image.width, image.height, 0])
    
    if not filtered_df.empty:
        if size_col != "Нет":
            sizes = (filtered_df[size_col] - filtered_df[size_col].min()) / (filtered_df[size_col].max() - filtered_df[size_col].min() + 1e-5) * 50 + 10
        else:
            sizes = 30
            
        scatter = ax.scatter(
            filtered_df['X'],
            filtered_df['Y'],
            c=filtered_df[color_col],
            cmap='RdYlGn',
            s=sizes,
            alpha=0.8,
            edgecolors='w',
            linewidth=0.5
        )
        
        cbar = fig.colorbar(scatter, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label(color_col, rotation=270, labelpad=15)
    else:
        ax.text(image.width/2, image.height/2, "Деревья не найдены\nИзмените параметры",
                ha='center', va='center', fontsize=20, color='white',
                bbox=dict(facecolor='black', alpha=0.7))

    ax.set_title(f"Пространственное распределение объектов древостоя ({species})")
    ax.axis('off')
    st.pyplot(fig)

with col2:
    st.subheader(" Сводная аналитика")
    st.metric("Всего деревьев в базе", len(df))
    st.metric("🎯 Отобрано по критериям", len(filtered_df))
    
    suitability = (len(filtered_df) / len(df) * 100) if len(df) > 0 else 0
    st.metric("Индекс пригодности территории", f"{suitability:.1f}%")
    
    st.markdown("---")
    st.markdown("** Показатели насаждения:**")
    st.metric("Площадь участка", f"{area_ha:.2f} га")
    st.metric("Полнота насаждения", f"{density_per_ha:.1f} м²/га")
    st.metric("Относительная полнота", f"{density_relative:.0f}%")
    st.metric("Запас древесины", f"{volume_per_ha:.1f} м³/га")
    
    st.markdown("---")
    st.markdown("**📊 Статистика по выборке:**")
    key_metrics = ['Высота, м', 'Диаметр ствола, см', 'Объём ствола, м3', 'Объём_расчётный_м3', 'Индекс виталитета']
    for col in key_metrics:
        if col in filtered_df.columns:
            st.write(f"Ср. {col}: **{filtered_df[col].mean():.2f}**")
    
    st.markdown("---")
    st.markdown("**🏷️ Распределение по классам:**")
    if not filtered_df.empty:
        tovarn_dist = filtered_df['Класс товарности'].value_counts()
        for cls, count in tovarn_dist.items():
            st.write(f"{cls}: **{count}** дер.")
    
    st.markdown("---")
    st.markdown("**🌱 Распределение по бонитету:**")
    if not filtered_df.empty:
        bonitet_dist = filtered_df['Бонитет'].value_counts().sort_index()
        for bon, count in bonitet_dist.items():
            st.write(f"Бонитет {bon}: **{count}** дер.")
    
    # Кнопка скачивания
    if not filtered_df.empty:
        st.markdown("---")
        st.markdown("**💾 Экспорт данных:**")
        csv = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Скачать отфильтрованные данные (CSV)",
            data=csv,
            file_name=f'filtered_trees_{species}_{datetime.now().strftime("%Y%m%d")}.csv',
            mime='text/csv',
        )

# --- РАЗДЕЛ С ОТЧЁТОМ ---
st.markdown("---")
st.subheader(" Сформировать отчёт по участку")

col_report1, col_report2 = st.columns(2)

with col_report1:
    st.markdown("**Параметры отчёта:**")
    report_title = st.text_input("Название участка:", value=f"Таксация {species}")
    report_date = st.date_input("Дата отчёта:", value=datetime.now())
    include_charts = st.checkbox("Включить графики", value=True)
    include_tables = st.checkbox("Включить таблицы", value=True)

with col_report2:
    st.markdown("**Содержание отчёта:**")
    include_summary = st.checkbox("Сводная аналитика", value=True)
    include_density = st.checkbox("Показатели полноты", value=True)
    include_volume = st.checkbox("Запас древесины", value=True)
    include_tovarnost = st.checkbox("Классы товарности", value=True)

if st.button(" Сформировать отчёт (Excel)", type="primary"):
    # Создаём Excel-файл с отчётом
    output = pd.ExcelWriter(f'отчет_{species}_{datetime.now().strftime("%Y%m%d")}.xlsx', engine='xlsxwriter')
    
    # Лист 1: Сводная информация
    summary_data = {
        'Параметр': [
            'Порода', 'Дата отчёта', 'Площадь участка, га',
            'Всего деревьев', 'Отобрано по критериям',
            'Полнота насаждения, м²/га', 'Относительная полнота, %',
            'Запас древесины, м³/га', 'Средняя высота, м',
            'Средний диаметр, см', 'Средний объём, м³'
        ],
        'Значение': [
            species, report_date.strftime('%d.%m.%Y'), f'{area_ha:.2f}',
            len(df), len(filtered_df),
            f'{density_per_ha:.1f}', f'{density_relative:.0f}',
            f'{volume_per_ha:.1f}', f'{filtered_df["Высота, м"].mean():.1f}',
            f'{filtered_df["Диаметр ствола, см"].mean():.1f}',
            f'{filtered_df["Объём_расчётный_м3"].mean():.3f}'
        ]
    }
    pd.DataFrame(summary_data).to_excel(output, sheet_name='Сводная информация', index=False)
    
    # Лист 2: Распределение по классам
    if include_tovarnost and not filtered_df.empty:
        tovarn_data = filtered_df['Класс товарности'].value_counts().reset_index()
        tovarn_data.columns = ['Класс товарности', 'Количество']
        tovarn_data.to_excel(output, sheet_name='Классы товарности', index=False)
    
    # Лист 3: Распределение по бонитету
    if not filtered_df.empty:
        bonitet_data = filtered_df['Бонитет'].value_counts().sort_index().reset_index()
        bonitet_data.columns = ['Бонитет', 'Количество']
        bonitet_data.to_excel(output, sheet_name='Бонитет', index=False)
    
    # Лист 4: Полные данные
    if include_tables:
        filtered_df.to_excel(output, sheet_name='Полные данные', index=False)
    
    output.close()
    
    st.success("✅ Отчёт сформирован! Скачайте файл ниже:")
    with open(f'отчет_{species}_{datetime.now().strftime("%Y%m%d")}.xlsx', 'rb') as f:
        st.download_button(
            label="📥 Скачать отчёт (Excel)",
            data=f,
            file_name=f'отчет_{species}_{datetime.now().strftime("%Y%m%d")}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
