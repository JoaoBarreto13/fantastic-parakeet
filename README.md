# Stremio Telegram Bot

Bot Telegram em Python que busca filmes e séries via Cinemeta, lista streams do Torrentio, baixa com `aria2c` e envia o arquivo como vídeo no Telegram. O projeto usa cache local em SQLite e reaproveita `file_id` quando disponível.

## Requisitos

- Python 3.11+
- `aria2c` instalado no sistema
- Acesso a um bot do Telegram via BotFather

## Instalação rápida

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip aria2

cd /caminho/para/o/projeto
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env
```

Crie os diretórios se ainda não existirem:

```bash
mkdir -p downloads cache_db logs
```

## Configuração

Preencha o arquivo `.env` com o token do bot e os IDs autorizados.

## Execução

```bash
source venv/bin/activate
python bot.py
```

## Rodando como serviço systemd

O arquivo [stremio-bot.service](stremio-bot.service) já está no repositório como modelo.

Antes de copiar para o sistema, edite estes campos no arquivo:

- `User=` e `Group=`: coloque o usuário Linux real que vai executar o bot
- `WorkingDirectory=`: caminho onde o projeto ficou instalado
- `EnvironmentFile=`: caminho do arquivo `.env`
- `ExecStart=`: caminho do Python dentro do `venv` e do `bot.py`

Exemplo usando a pasta sugerida no planejamento:

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
sudo journalctl -u stremio-bot -f
```

Se você instalou em outro diretório, ajuste os caminhos no `.service` antes de copiar.

## Comandos

- `/start` mostra ajuda
- `/buscar <título>` busca filme ou série
- `/cache` lista os últimos itens salvos no SQLite
- `/status` mostra uso de disco e tamanho do cache
- `/limpar [dias]` remove itens antigos do cache
- Texto livre também aciona busca

## Como funciona

1. O usuário envia uma busca.
2. O bot consulta a API da Cinemeta.
3. O usuário seleciona título, temporada e episódio quando aplicável.
4. O bot consulta o Torrentio e mostra streams disponíveis.
5. Ao baixar, o bot verifica o cache:
   - `tg_file_id` existente: reenvia direto pelo Telegram
   - arquivo local existente: reenvia do disco
   - sem cache: baixa com `aria2c`, envia e salva o resultado

## Banco de dados

O cache fica em SQLite no caminho configurado por `DB_PATH`.

Tabelas:

- `cache`
- `downloads`

## Variáveis de ambiente

Veja o arquivo `.env.example` para a lista completa.

## Observações

- O bot foi pensado para uso doméstico e lista fechada de usuários.
- O limite prático de envio pela Bot API é cerca de 2 GB.
- Se o `tg_file_id` expirar, o bot tenta reenviar a partir do arquivo local.

## Solução de problemas

- `aria2c: command not found`: instale com `sudo apt install aria2`
- Sem resultados na busca: tente o título em inglês
- Download travado: tente outro stream disponível
- Bot não inicia: verifique `BOT_TOKEN` e `ALLOWED_USERS` no `.env`
