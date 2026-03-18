# 🩺 TOUR.Doctor

An AI-powered Streamlit app that cleans, validates, and standardizes educational tour metadata for K–12 audiences.

## ✨ Features

* 🧠 Uses OpenAI to generate structured tour data
* 🌍 Supports English and French output
* 🏷️ Generates high-quality tags (EN + FR)
* ⚠️ Detects sensitive content (CW system)
* 📊 Provides accuracy scoring + confidence reasons
* 📁 Export as CSV or JSON
* 🎯 Designed for curriculum-safe content

---

## 🚀 Demo

Paste a messy tour record → get clean, structured output instantly.

---

## 🛠️ Tech Stack

* Python
* Streamlit
* OpenAI API

---

## 📦 Installation

```bash
git clone https://github.com/your-username/tour-doctor-app.git
cd tour-doctor-app
pip install -r requirements.txt
```

---

## 🔑 Environment Setup

Create a `.env` file:

```
OPENAI_API_KEY=your_api_key_here
```

---

## ▶️ Run the App

```bash
streamlit run app.py
```

---

## 📁 Project Structure

```
tour-doctor-app/
│── app.py
│── requirements.txt
│── .env (not included)
│── README.md
```

---

## ⚠️ Notes

* Do NOT commit your `.env` file
* Make sure `.gitignore` includes:

```
.env
__pycache__/
```

---

## 📌 Future Improvements

* Batch processing
* UI enhancements
* Deployment on Streamlit Cloud
* Admin review dashboard

---

## 👩‍💻 Author

Fatema

---

## 📄 License

N/A
