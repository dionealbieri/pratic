# Use a imagem oficial e leve do Python
FROM python:3.10-slim

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Copia as dependências e instala
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia as pastas do sistema para o container
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Cria a pasta do banco de dados (que será mapeada como volume persistente)
RUN mkdir -p /app/banco

# Expõe a porta que o FastAPI usa
EXPOSE 8000

# Comando para iniciar o servidor
CMD ["python", "backend/main.py"]
