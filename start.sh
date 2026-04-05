#!/bin/bash

# Carrega o .env removendo \r e aspas
export $(sed 's/\r//' .env | sed 's/"//g' | xargs)

echo "✅ Variáveis carregadas:"
echo "   OPENAI_BASE_URL=$OPENAI_BASE_URL"
echo "   OPENAI_MODEL=$OPENAI_MODEL"
echo ""
echo "🐾 Iniciando Claw Code Agent UI..."
echo ""

python -m streamlit run app.py
