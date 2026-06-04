# Stremio Telegram Bot

Bot Telegram em Python que busca filmes e séries via Cinemeta, lista streams do Torrentio, baixa com `aria2c`, comprime arquivos grandes com `ffmpeg` e envia o vídeo no Telegram. O projeto usa cache local em SQLite e reaproveita `tg_file_id` quando disponível.

## ⚠️ Projeto Pausado

Este projeto encontra-se pausado devido a alterações na API utilizada, o que impossibilitou a continuidade do funcionamento do bot.

Estou buscando uma nova abordagem e avaliando alternativas para substituir a dependência atual. Caso seja encontrada uma solução viável, o desenvolvimento será retomado.

Enquanto isso, o repositório permanecerá disponível para consulta e estudos.


### Instalação e execução — Linux (Debian/Ubuntu)

Pré-requisitos (ver seção acima): Python 3.11+, `aria2c`, `ffmpeg`.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip aria2 ffmpeg

cd /caminho/para/o/projeto
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env
```

Inicialização (Linux):

```bash
mkdir -p downloads cache_db logs
source venv/bin/activate
python bot.py
```

Rodando como serviço systemd

O arquivo [stremio-bot.service](stremio-bot.service) pode ser usado como modelo. Antes de copiar para o sistema, ajuste estes campos no arquivo:

- `User=` e `Group=`: usuário Linux que executará o bot
- `WorkingDirectory=`: caminho onde o projeto ficou instalado
- `EnvironmentFile=`: caminho do arquivo `.env`
- `ExecStart=`: caminho do Python dentro do `venv` e do `bot.py`

Exemplo usando `/opt/stremio-bot`:

```bash
sudo mkdir -p /opt/stremio-bot
sudo cp bot.py requirements.txt .env.example stremio-bot.service /opt/stremio-bot/
cd /opt/stremio-bot

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env
nano stremio-bot.service

sudo cp stremio-bot.service /etc/systemd/system/stremio-bot.service
sudo systemctl daemon-reload
sudo systemctl enable stremio-bot
sudo systemctl start stremio-bot
sudo systemctl status stremio-bot
```

### Instalação e execução — Windows (PowerShell / CMD)

1. Instale Python 3.11+ usando o instalador oficial e marque "Add Python to PATH".
2. Baixe os binários de `aria2` e `ffmpeg` e adicione as pastas que contêm `aria2c.exe` e `ffmpeg.exe` ao `PATH` do sistema (ou coloque os executáveis numa pasta já no PATH).

Exemplo mínimo (PowerShell):

```powershell
cd C:\caminho\para\o\projeto
python -m venv venv
# PowerShell
.\venv\Scripts\Activate.ps1
# se a política bloquear: Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
# no cmd.exe: venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
notepad .env
```

Verifique se os binários estão acessíveis:

```powershell
aria2c --version
ffmpeg -version
python --version
```

Se precisar adicionar ao PATH via PowerShell (reabra o terminal após):

```powershell
setx PATH "$env:PATH;C:\caminho\para\bin"
```

Nota sobre ambientes e serviços:

- É recomendável usar caminhos absolutos em serviços/Task Scheduler porque variáveis de ambiente do usuário podem não ser carregadas.
- Se usar um serviço, prefira um wrapper `.bat` ou um pequeno script que ative o `venv` e execute o `bot.py` para garantir que o ambiente virtual e variáveis do projeto sejam carregados.

Opções para rodar automaticamente:

- Task Scheduler (embutido): crie uma tarefa básica/avançada que execute um programa;
	- Program/script: `C:\caminho\para\venv\Scripts\python.exe`
	- Add arguments: `C:\caminho\para\projeto\bot.py`
	- Start in: `C:\caminho\para\projeto`
	- Configure para "Run whether user is logged on or not" e marque "Run with highest privileges" quando necessário.

- NSSM (Non-Sucking Service Manager): útil para transformar um comando em serviço Windows sem escrever código.

Exemplo rápido com NSSM (Prompt/Admin):

```powershell
nssm install stremio-bot "C:\caminho\para\venv\Scripts\python.exe" "C:\caminho\para\projeto\bot.py"
nssm set stremio-bot AppDirectory "C:\caminho\para\projeto"
nssm start stremio-bot
```

Se usar NSSM, no painel do serviço você também pode definir variáveis de ambiente específicas para o serviço (útil para apontar `DB_PATH`, `DOWNLOAD_DIR`, etc.).

Resumo: use caminhos absolutos, verifique `aria2c`/`ffmpeg`/`python` no PATH, e prefira um wrapper que ative o `venv` quando rodar como tarefa/serviço.
```powershell
aria2c --version
ffmpeg -version
python --version
```

Se precisar adicionar ao PATH via PowerShell (reabra o terminal após):

```powershell
setx PATH "$env:PATH;C:\caminho\para\bin"
```

Nota sobre ambientes e serviços:
- É recomendável usar caminhos absolutos em serviços/Task Scheduler porque variáveis de ambiente do usuário podem não ser carregadas.
- Se usar um serviço, prefira um wrapper `.bat` ou um pequeno script que ative o `venv` e execute o `bot.py` para garantir que o ambiente virtual e variáveis do projeto sejam carregados.

Opções para rodar automaticamente:

- Task Scheduler (embutido): crie uma tarefa básica/avançada que execute um programa;
	- Program/script: `C:\caminho\para\venv\Scripts\python.exe`
	- Add arguments: `C:\caminho\para\projeto\bot.py`
	- Start in: `C:\caminho\para\projeto`
	- Configure para "Run whether user is logged on or not" e marque "Run with highest privileges" quando necessário.

- NSSM (Non-Sucking Service Manager): útil para transformar um comando em serviço Windows sem escrever código.

Exemplo rápido com NSSM (Prompt/Admin):

```powershell
nssm install stremio-bot "C:\caminho\para\venv\Scripts\python.exe" "C:\caminho\para\projeto\bot.py"
nssm set stremio-bot AppDirectory "C:\caminho\para\projeto"
nssm start stremio-bot
```

Se usar NSSM, no painel do serviço você também pode definir variáveis de ambiente específicas para o serviço (útil para apontar `DB_PATH`, `DOWNLOAD_DIR`, etc.).

Resumo: use caminhos absolutos, verifique `aria2c`/`ffmpeg`/`python` no PATH, e prefira um wrapper que ative o `venv` quando rodar como tarefa/serviço.
```

### Inicialização

```bash
mkdir -p downloads cache_db logs
source venv/bin/activate
python bot.py
```

### Rodando como serviço systemd

O arquivo [stremio-bot.service](stremio-bot.service) pode ser usado como modelo.

Antes de copiar para o sistema, ajuste estes campos no arquivo:

- `User=` e `Group=`: usuário Linux que executará o bot
- `WorkingDirectory=`: caminho onde o projeto ficou instalado
- `EnvironmentFile=`: caminho do arquivo `.env`
- `ExecStart=`: caminho do Python dentro do `venv` e do `bot.py`

Exemplo usando `/opt/stremio-bot`:

```bash
sudo mkdir -p /opt/stremio-bot
sudo cp bot.py requirements.txt .env.example stremio-bot.service /opt/stremio-bot/
cd /opt/stremio-bot

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env
nano stremio-bot.service

sudo cp stremio-bot.service /etc/systemd/system/stremio-bot.service
sudo systemctl daemon-reload
sudo systemctl enable stremio-bot
sudo systemctl start stremio-bot
sudo systemctl status stremio-bot
```

## Fluxo

### Busca

- `/start` mostra uma ajuda curta.
- `/buscar <título>` faz a busca principal.
- Texto livre também dispara a busca.
- O bot consulta Cinemeta e retorna botões com título, ano, diretor/cast e nota.

### Seleção

- Para filmes, o bot vai direto para os streams.
- Para séries, o bot mostra temporada e episódio.
- O usuário escolhe um stream e o download começa.

### Download

- Downloads são feitos com `aria2c`.
- Se o mesmo usuário tentar iniciar outro download, o bot bloqueia e pede para aguardar.
- O mesmo conteúdo também é protegido por lock para evitar downloads duplicados simultâneos.

### Legendas

- O bot procura `.srt` e `.ass` dentro do diretório baixado.
- A ordem de preferência vem de `SUB_LANG`, por exemplo: `pt-br,pt,en`.
- Se encontrar uma legenda preferida, o bot renomeia para casar com o vídeo e envia automaticamente.
- Se não encontrar uma legenda preferida, o bot mostra opções para escolha manual.
- A cópia temporária da legenda pode ser mantida com `KEEP_SUBTITLE_COPY=true`.

### Compressão

- Arquivos acima de 2 GB entram em fila de compressão em segundo plano.
- A compressão usa `ffmpeg` com `crf` e `preset` configuráveis via `.env` se você decidir expor essas opções futuramente.
- Se o arquivo comprimido ainda ficar acima do limite da Bot API, o bot avisa o caminho local.

## Limpeza

### Comando manual

- `/limpar [dias]` remove entradas antigas do cache e apaga os arquivos associados.
- Se nenhum valor for informado, o padrão é 30 dias.

### O que é limpo

- Entradas antigas da tabela `cache`.
- Arquivos locais relacionados àquelas entradas, quando ainda existirem.
- Cópias temporárias de legendas são removidas automaticamente após envio, salvo se `KEEP_SUBTITLE_COPY=true`.

### Recomendações

- Aponte `DOWNLOAD_DIR` para um volume com espaço suficiente.
- Faça manutenção periódica do cache se o uso for contínuo.

## Compressão

### Quando acontece

- Assim que o arquivo final baixado ultrapassa 2 GB.
- O bot enfileira a compressão sem bloquear o handler principal.

### Comportamento esperado

- O usuário recebe aviso de que a compressão foi enfileirada.
- O worker processa a compressão em background.
- Se a versão comprimida couber no limite, ela é enviada.
- Se não couber, o bot salva o caminho local e informa o usuário.

### Dependências

- `ffmpeg` precisa estar instalado no sistema.
- O bot avisa claramente se `ffmpeg` não estiver disponível.

## Troubleshooting

- `aria2c: command not found`: instale com `sudo apt install aria2`.
- `ffmpeg não instalado`: instale com `sudo apt install ffmpeg`.
- Sem resultados na busca: tente o título em inglês.
- Download travado: tente outro stream disponível.
- Bot não inicia: verifique `BOT_TOKEN` e `ALLOWED_USERS` no `.env`.
- A legenda não aparece como esperado: confira `SUB_LANG` e o nome dos arquivos `.srt/.ass`.
- O bot envia o vídeo, mas não a legenda escolhida: veja os logs em `logs/bot.log`.
- O arquivo ficou grande demais mesmo após compressão: verifique o caminho local informado pelo bot.

## Logs

- Os logs ficam em `logs/bot.log`.
- A rotação está habilitada por padrão.
- O tamanho máximo e o número de backups podem ser ajustados no `.env` com `LOG_MAX_BYTES` e `LOG_BACKUP_COUNT`.

## Comandos

- `/start` mostra ajuda.
- `/buscar <título>` busca filme ou série.
- `/cache` lista os últimos itens salvos no SQLite.
- `/status` mostra uso de disco e tamanho do cache.
- `/limpar [dias]` remove itens antigos do cache.
- Texto livre também aciona busca.

## Banco de Dados

O cache fica em SQLite no caminho configurado por `DB_PATH`.

Tabelas principais:

- `cache`
- `downloads`

## Variáveis de Ambiente

Veja o arquivo [.env.example](.env.example) para a lista completa.

Resumo das principais variáveis:

- `BOT_TOKEN`: token do bot.
- `ALLOWED_USERS`: IDs autorizados.
- `DOWNLOAD_DIR`: diretório onde os vídeos são baixados.
- `DB_PATH`: caminho do banco SQLite.
- `DEFAULT_QUALITY`: qualidade preferida.
- `SUB_LANG`: prioridade de idioma das legendas.
- `KEEP_SUBTITLE_COPY`: mantém ou remove a cópia temporária da legenda.
- `LOG_MAX_BYTES`: tamanho máximo do arquivo de log antes da rotação.
- `LOG_BACKUP_COUNT`: quantidade de backups mantidos.

## Observações

- O bot foi pensado para uso doméstico e lista fechada de usuários.
- O limite prático de envio pela Bot API é cerca de 2 GB.
- Se o `tg_file_id` expirar, o bot tenta reenviar a partir do arquivo local.
- O fluxo de legenda pode ser automático ou manual, conforme a preferência configurada.
