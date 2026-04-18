FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema (terraform para validacion)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Instalar Terraform para validacion automatica de HCL
RUN curl -fsSL https://releases.hashicorp.com/terraform/1.7.0/terraform_1.7.0_linux_amd64.zip \
    -o /tmp/terraform.zip \
    && unzip /tmp/terraform.zip -d /usr/local/bin/ \
    && rm /tmp/terraform.zip

# Copiar proyecto
COPY pyproject.toml .
COPY agentforge/ ./agentforge/
COPY templates/ ./templates/

# Instalar dependencias Python
RUN pip install --no-cache-dir -e .

CMD ["python3", "-m", "agentforge.server"]
