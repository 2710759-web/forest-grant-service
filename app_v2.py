import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from PIL import Image
import io

# Настройка страницы
st.set_page_config(page_title="ЛесАналитика БПЛА", layout="wide")

# Заголовок
st.title(" Модуль аналитического выявления древостоя")
st.markdown("---")

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

# Демо-режим по умолчанию
demo_mode = st.sidebar.checkbox("Использовать демо-данные", value=False)

# --- ЗАГРУЗКА ДАННЫХ ---
if demo_mode:
    # Демо-режим (старые файлы)
    try:
        image = Image.open("forest.jpg")
        df = pd.read_excel("trees.xlsx")
        st.sidebar.success("Загружены демо-данные")
    except:
        st.error("Демо-файлы не найдены. Пожалуйста, загрузите свои файлы.")
        st.stop()
else:
    # Режим загрузки пользователем
    if uploaded_image is None or uploaded_xlsx is None:
        st.info("👆 Пожалуйста, загрузите ортофотоплан и таблицу с данными слева, или включите демо-режим")
        st.stop()
    
    try:
        image = Image.open(uploaded_image)
        df = pd.read_excel(uploaded_xlsx)
        st.sidebar.success("Файлы успешно загружены!")
    except Exception as e:
        st.error(f"Ошибка при чтении файлов: {e}")
        st.stop()

# Проверяем наличие колонок X и Y
if 'X' not in df.columns or 'Y' not in df.columns:
    st.error("❌ Ошибка: В таблице Excel должны быть колонки с точными названиями 'X' и 'Y'.")
    st.stop()

# Находим все числовые колонки для фильтров (кроме X и Y)
numeric_cols = [col for col in df.select_dtypes(include=['number']).columns if col not in ['X', 'Y']]

# --- БОКОВАЯ ПАНЕЛЬ С НАСТРОЙКАМИ ---
st.sidebar.markdown("---")
st.sidebar.header("⚙️ Параметры фильтрации")

# 1. Выбор параметра для цвета точек
color_col = st.sidebar.selectbox("Параметр для цветовой индикации:", numeric_cols, index=0)
# 2. Выбор параметра для размера точек (опционально)
size_col = st.sidebar.selectbox("Параметр для размера точек:", ["Нет"] + numeric_cols, index=0)

# 3. Ползунки для пороговых значений
st.sidebar.markdown("**Пороговые значения:**")
filters = {}
for col in numeric_cols:
    min_val = float(df[col].min())
    max_val = float(df[col].max())
    # Если значения одинаковые, чтобы слайдер не сломался
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

# --- ФИЛЬТРАЦИЯ ДАННЫХ ---
filtered_df = df.copy()
for col, (min_t, max_t) in filters.items():
    filtered_df = filtered_df[(filtered_df[col] >= min_t) & (filtered_df[col] <= max_t)]

# --- ИНФОРМАЦИЯ О ЗАГРУЖЕННЫХ ФАЙЛАХ ---
if not demo_mode:
    st.sidebar.markdown("---")
    st.sidebar.markdown("**📊 Информация о файлах:**")
    st.sidebar.write(f"Изображение: {uploaded_image.name}")
    st.sidebar.write(f"Таблица: {uploaded_xlsx.name}")
    st.sidebar.write(f"Размер изображения: {image.width} × {image.height} px")
    st.sidebar.write(f"Записей в таблице: {len(df)}")

# --- ВИЗУАЛИЗАЦИЯ ---
col1, col2 = st.columns([3, 1])

with col1:
    st.subheader("️ Карта выделенных территорий")
    
    fig, ax = plt.subplots(figsize=(12, 8))
    # Рисуем подложку (снимок)
    ax.imshow(image, extent=[0, image.width, image.height, 0])
    
    # Рисуем точки деревьев
    if not filtered_df.empty:
        # Определяем размеры точек
        if size_col != "Нет":
            sizes = (filtered_df[size_col] - filtered_df[size_col].min()) / (filtered_df[size_col].max() - filtered_df[size_col].min() + 1e-5) * 50 + 10
        else:
            sizes = 30
            
        # Строим scatter plot поверх картинки
        scatter = ax.scatter(
            filtered_df['X'], 
            filtered_df['Y'], 
            c=filtered_df[color_col], 
            cmap='RdYlGn', # Градиент от красного к зеленому
            s=sizes, 
            alpha=0.8, 
            edgecolors='w', 
            linewidth=0.5
        )
        
        # Добавляем легенду цвета
        cbar = fig.colorbar(scatter, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label(color_col, rotation=270, labelpad=15)
    else:
        ax.text(image.width/2, image.height/2, "Деревья не найдены\nИзмените параметры", 
                ha='center', va='center', fontsize=20, color='white', 
                bbox=dict(facecolor='black', alpha=0.7))

    ax.set_title("Пространственное распределение объектов древостоя")
    ax.axis('off') # Скрываем оси координат для чистого вида
    st.pyplot(fig)

with col2:
    st.subheader(" Сводная аналитика")
    st.metric("Всего деревьев в базе", len(df))
    st.metric("🎯 Отобрано по критериям", len(filtered_df))
    
    # Считаем "пригодность" (процент отфильтрованных)
    suitability = (len(filtered_df) / len(df)) * 100 if len(df) > 0 else 0
    st.metric("Индекс пригодности территории", f"{suitability:.1f}%")
    
    st.markdown("---")
    st.markdown("**Статистика по выборке:**")
    for col in numeric_cols[:3]: # Показываем среднее по первым 3 параметрам
        st.write(f"Ср. {col}: **{filtered_df[col].mean():.2f}**")
    
    # Кнопка скачивания результатов
    if not filtered_df.empty:
        st.markdown("---")
        st.markdown("**💾 Экспорт данных:**")
        
        # Конвертируем в CSV для скачивания
        csv = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Скачать отфильтрованные данные (CSV)",
            data=csv,
            file_name='filtered_trees.csv',
            mime='text/csv',
        )
