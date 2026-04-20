# FocusGuard

Sistema completo anti-procrastinação integrado com Home Assistant, monitoramento de janelas no Windows e Google Tasks. Focado em estudantes e residentes (configurado nativamente para Oftalmologia).

## Arquitetura

O sistema é dividido em 3 componentes:

1. **Backend (FastAPI)**: Orquestrador central, conecta-se ao Home Assistant, Google Tasks e gerencia o banco de dados SQLite. Serve o Dashboard Web.
2. **Tracker (Windows)**: Aplicação que roda silenciosamente (System Tray), monitora a janela ativa e envia dados para o backend via API.
3. **Dashboard Web**: Interface SPA em Dark Mode para visualização de métricas e gerenciamento.

## Estratégia de Identificação de Estudo (Oftalmologia)

O FocusGuard calcula dinamicamente seu **Tempo Útil** baseado em:
- Visita ao Hospital (via zonas do Home Assistant).
- Cálculo: `(22:00 - Horário que chegou em casa) * 2/3`.
- Exemplo: Chegou às 19:00. Tempo até as 22h = 3 horas. Tempo Útil = 2 horas de estudo requeridas.

A detecção de estudo é feita lendo os títulos das janelas ativas e procurando por palavras-chave relacionadas à Oftalmologia (Retina, Glaucoma, OCT, etc.) configuradas no `config.yaml`.

## Instalação e Execução

### 1. Pré-requisitos
- Python 3.9+
- Ambiente Windows (para o Tracker)

### 2. Configurar o Backend
1. Navegue até a pasta do projeto.
2. Crie um ambiente virtual e ative-o.
3. Instale as dependências do backend:
   ```bash
   pip install -r backend/requirements.txt
   ```
4. Edite o arquivo `config.yaml` na raiz com:
   - Sua URL do Home Assistant e Token de Acesso Longo.
   - O `entity_id` da sua pessoa (ex: `person.matheus_galvao`).
5. Inicie o servidor:
   ```bash
   python -m backend.main
   ```
6. (Google Tasks): Na primeira execução que tentar acessar as tarefas, o backend precisará do arquivo `data/credentials.json` (gerado no Google Cloud Console). Ele abrirá uma janela no navegador para você autorizar o aplicativo.

### 3. Configurar o Tracker (Windows)
1. Em um novo terminal, certifique-se de estar no mesmo ambiente virtual.
2. Instale as dependências do tracker:
   ```bash
   pip install -r tracker/requirements.txt
   ```
3. Execute o tracker:
   ```bash
   python -m tracker.main
   ```
4. Um ícone aparecerá na bandeja do sistema (System Tray) indicando o status atual.

### 4. Acessar o Dashboard
Com o backend rodando, acesse:
**http://localhost:8000**
