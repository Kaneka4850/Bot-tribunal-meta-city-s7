# Usa uma imagem oficial leve do Python 3.13
FROM python:3.13-slim

# Evita que o Python grave arquivos .pyc no disco (economiza espaço)
ENV PYTHONDONTWRITEBYTECODE=1
# Força o Python a exibir os logs instantaneamente no console (sem buffer)
ENV PYTHONUNBUFFERED=1

# Cria o diretório de trabalho do aplicativo
WORKDIR /app

# Copia apenas o arquivo de dependências primeiro,
# para aproveitar o cache do Docker nas próximas builds se as dependências não mudarem
COPY requirements.txt .

# Instala as dependências sem guardar cache do instalador (deixa a imagem menor)
RUN pip install --no-cache-dir -r requirements.txt

# Cria o diretório seguro para o banco de dados e configura o symlink.
# Como o código espera que o banco esteja na raiz (/app/stmc.db),
# criamos um atalho que aponta para /data, onde configuraremos o volume persistente.
RUN mkdir /data && ln -s /data/stmc.db /app/stmc.db

# Copia todo o restante do código do projeto para o contêiner
COPY . .

# Comando de inicialização do bot apontando para o arquivo principal
CMD ["python", "main.py"]
