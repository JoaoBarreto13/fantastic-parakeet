# 🎬 Stremio Telegram Bot — Planejamento Completo

> Documento de referência para uso no **Cowork / Codex / Claude Code**.
> Contém toda a arquitetura, fluxos, tarefas e contexto necessário para implementar, evoluir e manter o bot do zero.

---

## 📌 Visão Geral do Projeto

**Objetivo:** Bot para Telegram que busca filmes e séries via Torrentio (addon do Stremio), faz o download no servidor local e envia o arquivo de vídeo como mídia diretamente no Telegram. Possui cache inteligente em dois níveis para evitar downloads repetidos.

**Usuários-alvo:** Família e amigos próximos (lista fechada de IDs autorizados).

**Princípios:**
- 100% gratuito (sem Real-Debrid, sem serviços pagos)
- Roda em Linux local (PC ou servidor doméstico)
- Prioridade para qualidade 1080p
- Cache local + cache via `file_id` do Telegram

---

## 🗂️ Estrutura de Arquivos do Projeto

```
stremio-bot/
│
├── bot.py                  # Código principal do bot
├── requirements.txt        # Dependências Python
├── .env                    # Configurações sensíveis (não versionar)
├── .env.example            # Modelo de configuração
├── stremio-bot.service     # Serviço systemd para auto-inicialização
├── README.md               # Guia de instalação e uso
│
├── downloads/              # Vídeos baixados (pode crescer muito — mapeie para HD externo)
├── cache_db/
│   └── cache.db            # Banco SQLite com histórico de downloads e cache
└── logs/
    └── bot.log             # Logs de execução
```

---

## 🏗️ Arquitetura e Fluxo Principal

```
┌─────────────────────────────────────────────────────────────────┐
│                        USUÁRIO (Telegram)                        │
└──────────────────────────────┬──────────────────────────────────┘
                               │ /buscar <título> ou texto livre
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     BOT PYTHON (bot.py)                          │
│                                                                   │
│  1. Verifica autorização (ALLOWED_USERS)                         │
│  2. Busca título na API Cinemeta (Stremio)                       │
│  3. Apresenta resultados com InlineKeyboard                      │
│  4. Usuário seleciona: título → temporada → episódio             │
│  5. Busca streams no Torrentio API                               │
│  6. Filtra por qualidade preferida (1080p default)               │
│  7. Apresenta opções de stream com tamanho estimado              │
└──────────────────────────────┬──────────────────────────────────┘
                               │ usuário clica em "⬇️ baixar"
               ┌───────────────┴───────────────┐
               │                               │
       ┌───────▼───────┐               ┌───────▼───────┐
       │  CACHE HIT    │               │  CACHE MISS   │
       │               │               │               │
       │ tg_file_id?   │               │ aria2c baixa  │
       │  → envia      │               │ o torrent     │
       │  instantâneo  │               │               │
       │               │               │ Arquivo salvo │
       │ arquivo local?│               │ em downloads/ │
       │  → re-envia   │               │               │
       └───────────────┘               │ Envia via Bot │
                                       │ API Telegram  │
                                       │               │
                                       │ Salva file_id │
                                       │ no SQLite     │
                                       └───────────────┘
```

---

## 🔌 Integrações Externas

### 1. Cinemeta API (busca de títulos)
- **Base URL:** `https://v3-cinemeta.strem.io`
- **Endpoint filmes:** `GET /catalog/movie/top/search={query}.json`
- **Endpoint séries:** `GET /catalog/series/top/search={query}.json`
- **Retorna:** lista de `metas` com `id` (IMDB ID), `name`, `type`, `year`
- **Sem autenticação necessária**

### 2. Torrentio API (busca de streams/torrents)
- **Base URL:** `https://torrentio.strem.fun`
- **Endpoint filme:** `GET /stream/movie/{imdb_id}.json`
- **Endpoint série:** `GET /stream/series/{imdb_id}:{season}:{episode}.json`
- **Retorna:** lista de `streams` com `infoHash`, `name`, `title`
- **Sem autenticação necessária**
- **Observação:** pode ter rate limiting — implementar retry com backoff

### 3. aria2c (download de torrents)
- **Instalação:** `sudo apt install aria2`
- **Parâmetros chave:**
  - `--seed-time=0` — não faz seeding após download
  - `--bt-stop-timeout=300` — para após 5 min sem progresso
  - `--max-connection-per-server=4`
  - `--file-allocation=none` — mais rápido no início
- **Output:** maior arquivo de vídeo no diretório de destino

### 4. Telegram Bot API
- **Library:** `python-telegram-bot==21.6`
- **Limite de arquivo:** 2 GB (Bot API) / 4 GB (Telegram Premium)
- **file_id:** reutilizável para reenvio sem re-upload
- **Timeouts para upload de vídeo:** `write_timeout=600`, `read_timeout=600`

---

## 🗄️ Banco de Dados (SQLite)

### Tabela `cache`

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK | Auto-incremento |
| `query` | TEXT | Título buscado |
| `imdb_id` | TEXT | ID do IMDB (ex: `tt0944947`) |
| `season` | INTEGER | Temporada (NULL para filmes) |
| `episode` | INTEGER | Episódio (NULL para filmes) |
| `quality` | TEXT | `1080p`, `720p`, etc. |
| `file_path` | TEXT | Caminho absoluto no servidor |
| `file_size` | INTEGER | Tamanho em bytes |
| `tg_file_id` | TEXT | file_id do Telegram (reuso) |
| `created_at` | TEXT | Timestamp |

### Tabela `downloads`

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK | Auto-incremento |
| `user_id` | INTEGER | Telegram user ID |
| `query` | TEXT | O que foi pedido |
| `status` | TEXT | `pending`, `downloading`, `done`, `failed` |
| `started_at` | TEXT | Timestamp início |
| `finished_at` | TEXT | Timestamp fim |

---

## ⚙️ Variáveis de Ambiente (.env)

| Variável | Obrigatória | Descrição | Exemplo |
|---|---|---|---|
| `BOT_TOKEN` | ✅ | Token do BotFather | `7123...AAF` |
| `ALLOWED_USERS` | ✅ | IDs separados por vírgula | `123456,789012` |
| `DOWNLOAD_DIR` | ❌ | Diretório de downloads | `./downloads` |
| `DB_PATH` | ❌ | Caminho do SQLite | `./cache_db/cache.db` |
| `DEFAULT_QUALITY` | ❌ | Qualidade padrão | `1080p` |

---

## 📱 Comandos do Bot

| Comando | Argumentos | Descrição |
|---|---|---|
| `/start` | — | Mostra ajuda e comandos disponíveis |
| `/buscar` | `<título>` | Busca filme ou série pelo nome |
| `/cache` | — | Lista os últimos 20 itens em cache |
| `/status` | — | Espaço em disco, total de itens no cache |
| `<texto livre>` | — | Qualquer mensagem também aciona busca |

### Fluxo de Interação (InlineKeyboard)

```
/buscar Breaking Bad
    └─ [📺 Breaking Bad (2008)]      ← callback: action=select
         └─ [Temporada 1] [Temporada 2] ...    ← action=season
              └─ [1][2][3]...[24]              ← action=episode
                   └─ [⬇️ 1080p • 4.2 GB • YTS]  ← action=download
```

---

## 🧠 Lógica de Cache (2 Níveis)

```python
# Nível 1: tg_file_id (mais rápido — Telegram serve do próprio CDN)
if tg_file_id exists in DB:
    bot.send_video(video=tg_file_id)  # instantâneo

# Nível 2: arquivo local (sem re-download)
elif file_path exists on disk:
    bot.send_video(video=open(file_path))  # lê do disco

# Sem cache: faz download
else:
    aria2c download → salva → envia → salva tg_file_id
```

**Limpeza de cache (a implementar):** comando `/limpar` para remover arquivos com mais de N dias e liberar espaço.

---

## 🔒 Autenticação e Segurança

- Lista de `ALLOWED_USERS` no `.env` — apenas esses IDs conseguem usar o bot
- Decorator `@require_auth` aplicado em todos os handlers
- `.env` **nunca** deve ser versionado no Git (adicionar ao `.gitignore`)
- Token do bot deve ser revogado e regenerado se comprometido (via @BotFather)

---

## 🚀 Instalação no Servidor Linux

### Pré-requisitos do sistema

```bash
sudo apt update && sudo apt install -y \
  python3 python3-pip python3-venv \
  aria2 \
  ffmpeg          # opcional: para compressão futura
```

### Setup do projeto

```bash
# Copiar arquivos para o servidor
mkdir -p /opt/stremio-bot
cp bot.py requirements.txt .env.example /opt/stremio-bot/
cd /opt/stremio-bot

# Ambiente virtual Python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configuração
cp .env.example .env
nano .env  # preencher BOT_TOKEN e ALLOWED_USERS

# Criar diretórios
mkdir -p downloads cache_db logs
```

### Rodar como serviço systemd

```bash
# Editar stremio-bot.service: substituir %i pelo usuário Linux
nano stremio-bot.service

sudo cp stremio-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable stremio-bot
sudo systemctl start stremio-bot

# Monitorar
sudo systemctl status stremio-bot
sudo journalctl -u stremio-bot -f
```

---

## 🗺️ Roadmap de Funcionalidades

### ✅ Fase 1 — MVP (implementado)
- [x] Busca de filmes e séries via Cinemeta
- [x] Streams via Torrentio (gratuito, sem Real-Debrid)
- [x] Download via aria2c
- [x] Envio como vídeo no Telegram
- [x] Cache em SQLite (arquivo local + tg_file_id)
- [x] Lista de usuários autorizados
- [x] Filtro por qualidade (1080p padrão)
- [x] Serviço systemd para auto-início

### 🔲 Fase 2 — Melhorias de UX
- [ ] **Desambiguação de títulos iguais** — mostrar diretor + rating IMDB no botão (`🎬 Batman • 1989 • Tim Burton • ⭐7.5`)
- [ ] **Retomada de download** — flag `--continue=true` no aria2c para aproveitar arquivos parciais
- [ ] `/limpar` — limpar cache com mais de N dias
- [ ] `/baixados` — listar arquivos com botões para reenviar
- [ ] Notificação de progresso mais granular (% a cada 5%)
- [ ] Seleção de idioma de legenda (quando disponível no torrent)
- [ ] Botão "Cancelar" durante download em andamento
- [ ] Confirmação de qualidade com prévia do tamanho antes de baixar

### 🔲 Fase 3 — Gestão de Espaço
- [ ] Alerta automático quando disco ficar com menos de 10 GB livres
- [ ] Limpeza automática de arquivos acessados há mais de 30 dias
- [ ] Comando `/disco` com visualização do espaço por título
- [ ] Suporte a HD externo / mount point configurável

### 🔲 Fase 4 — Features Avançadas
- [ ] Suporte a legendas `.srt` / `.ass` (baixar separado e enviar junto)
- [ ] Compressão automática com FFmpeg para arquivos > 2 GB
- [ ] Suporte a Telegram Premium (upload de até 4 GB)
- [ ] Fila de downloads (evitar múltiplos downloads simultâneos)
- [ ] Histórico por usuário (`/meu_historico`)
- [ ] Agendamento: "avisa quando sair o próximo episódio"

---

## 🎭 Tratamento de Títulos com Nomes Iguais

### O problema

Vários filmes/séries compartilham o mesmo nome mas são obras diferentes. Exemplos reais:

| Nome | Versões existentes |
|---|---|
| Batman | 1966 (Adam West), 1989 (Tim Burton), 2022 (Robert Pattinson) |
| Dune | 1984 (David Lynch), 2021 (Denis Villeneuve) |
| Scarface | 1932 (original), 1983 (Al Pacino) |
| The Mummy | 1932, 1999, 2017 |
| It | 1990 (minissérie), 2017 (filme) |

### Por que o cache NÃO tem colisão

O cache usa `imdb_id` como chave primária — e cada obra tem um IMDB ID **único e imutável**:

```
Batman (1989)  →  tt0096895
Batman (2022)  →  tt1877830  ← chave diferente, sem colisão
```

Mesmo que o usuário baixe os dois, ficam em entradas separadas no SQLite. ✅

### Onde SIM existe ambiguidade — na busca

O problema real está na etapa de **seleção**: quando o Cinemeta retorna múltiplos resultados com nomes iguais, o botão só mostra `🎬 Batman (1989)` e `🎬 Batman (2022)` — o usuário pode não saber qual é qual sem mais contexto.

### Solução implementada (a fazer no bot.py)

Enriquecer o label do botão com dados extras da resposta do Cinemeta:

```python
# Antes (ambíguo):
label = f"🎬 Batman (1989)"

# Depois (claro):
label = f"🎬 Batman (1989) • Tim Burton • ⭐7.5"
#                            ↑ diretor       ↑ rating IMDB
```

Campos disponíveis no objeto `meta` do Cinemeta:

| Campo | Exemplo | Uso no label |
|---|---|---|
| `name` | `"Batman"` | Nome principal |
| `year` | `1989` | Ano de lançamento |
| `director` | `["Tim Burton"]` | Distingue remakes |
| `imdbRating` | `"7.5"` | Qualidade percebida |
| `type` | `"movie"` / `"series"` | Emoji 🎬 ou 📺 |
| `genres` | `["Action","Crime"]` | Contexto adicional |
| `description` | `"Bruce Wayne..."` | Exibir como caption |

### Formato final do botão de busca

```
🎬 Batman • 1989 • Tim Burton • ⭐7.5
🎬 Batman • 2022 • Matt Reeves • ⭐7.8
📺 Batman • 1966 • série • ⭐7.4
```

### Segundo cenário: mesmo filme, qualidades diferentes no cache

Se o usuário baixar `Batman (2022)` em `1080p` e depois pedir em `720p`, o cache trata como entradas separadas (chave inclui `quality`). Se pedir `1080p` de novo, vai direto do cache. Sem colisão. ✅

### Terceiro cenário: mesmo IMDB ID, arquivo baixado duas vezes

Pode acontecer se o usuário cancelar e reiniciar. Tratamento:

```python
# Ao iniciar download, verificar se já existe arquivo no diretório destino
if dest.exists() and any(dest.glob("**/*.mkv")):
    # Aproveita arquivo parcial ou completo já existente
    # aria2c retoma automaticamente com --continue=true
```

Flag a adicionar no aria2c: `--continue=true` — retoma downloads incompletos sem re-baixar do zero.

---

## 🐛 Problemas Conhecidos e Soluções

| Problema | Causa | Solução |
|---|---|---|
| Arquivo > 2 GB não envia | Limite da Bot API | Comprimir com FFmpeg ou usar Telegram Premium |
| "Nenhum resultado" na busca | Título em português | Buscar sempre em inglês |
| Download trava | Torrent sem seeders | Tentar outro stream da lista |
| `aria2c: command not found` | Não instalado | `sudo apt install aria2` |
| Bot para de responder | Crash / reinicialização | systemd reinicia automaticamente |
| tg_file_id expirado | Telegram limpa arquivos antigos | Re-envia do arquivo local automaticamente |
| Dois filmes com mesmo nome | Label do botão sem contexto | Mostrar diretor + rating no botão (ver seção acima) |
| Download reiniciado pelo usuário | Arquivo parcial no disco | Adicionar `--continue=true` no aria2c |

---

## 📦 Dependências Python

```
python-telegram-bot==21.6   # Framework do bot Telegram
httpx==0.27.2               # Requisições HTTP assíncronas
python-dotenv==1.0.1        # Leitura do .env
```

**Dependências do sistema:**
- `aria2` — cliente BitTorrent para linha de comando
- `python3.11+` — versão mínima do Python
- `ffmpeg` — opcional, para compressão de vídeo futura

---

## 🧪 Testes Manuais

### Verificar se Torrentio está respondendo
```bash
curl "https://torrentio.strem.fun/stream/movie/tt1375666.json" | python3 -m json.tool | head -40
```

### Verificar se Cinemeta está respondendo
```bash
curl "https://v3-cinemeta.strem.io/catalog/movie/top/search=inception.json" | python3 -m json.tool | head -40
```

### Testar download manual com aria2c
```bash
aria2c --seed-time=0 --dir=/tmp/test "magnet:?xt=urn:btih:HASH_AQUI"
```

### Ver logs do bot em tempo real
```bash
tail -f /opt/stremio-bot/logs/bot.log
```

---

## 📐 Decisões de Arquitetura

| Decisão | Alternativa considerada | Motivo da escolha |
|---|---|---|
| `aria2c` para download | `libtorrent` (Python) | aria2c é mais simples, sem deps compiladas, mais estável |
| SQLite para cache | Redis, PostgreSQL | Sem infraestrutura adicional, suficiente para uso doméstico |
| `python-telegram-bot` | `aiogram`, `pyTelegramBotAPI` | Mais madura, async nativo, boa documentação |
| Torrentio (gratuito) | Real-Debrid (pago) | Custo zero, funciona bem para 1080p |
| Cinemeta para busca | TMDB API | Já integrado ao ecossistema Stremio, sem API key necessária |

---

## 🔑 Como Obter Credenciais

### Token do Bot Telegram
1. Abra o Telegram e busque `@BotFather`
2. Envie `/newbot`
3. Escolha um nome e um username (ex: `MeuStreamBot`)
4. Copie o token gerado: `7123456789:AAFxxxxx...`

### IDs dos usuários autorizados
1. No Telegram, envie `/start` para `@userinfobot`
2. O bot retorna seu ID numérico
3. Peça para cada familiar/amigo fazer o mesmo e te enviar o número

---

## 🤖 Contexto para IA (Cowork / Codex / Claude Code)

> Use esta seção como contexto inicial ao abrir uma sessão no Cowork ou passar para uma IA de código.

**Stack:** Python 3.11, `python-telegram-bot 21.6`, `httpx`, `sqlite3`, `aria2c`

**O que o projeto faz:**
Bot Telegram que recebe pedidos de filmes/séries, busca streams gratuitos via API do Torrentio (addon Stremio), baixa via aria2c e envia o arquivo como vídeo no Telegram. Tem cache em SQLite (arquivo local + tg_file_id do Telegram).

**Arquivo principal:** `bot.py` — tudo em um único arquivo por simplicidade.

**Padrões adotados:**
- Handlers assíncronos (`async/await`)
- `InlineKeyboardMarkup` para navegação (título → temporada → episódio → qualidade)
- Decorator `@require_auth` em todos os handlers públicos
- Funções `db_*` para todas as operações no SQLite

**Para evoluir o projeto:**
- Qualquer nova funcionalidade deve seguir o padrão de handlers existente
- Novos comandos devem ser registrados em `app.add_handler(CommandHandler(...))`
- Novas tabelas devem ser criadas em `init_db()`
- Manter compatibilidade com Python 3.11+

**Para rodar localmente:**
```bash
cd /opt/stremio-bot
source venv/bin/activate
python bot.py
```

**Para ver o que já está em cache:**
```bash
sqlite3 cache_db/cache.db "SELECT query, quality, file_size, tg_file_id IS NOT NULL as has_tg_id FROM cache;"
```

---

## 📡 Exemplos Reais de Resposta das APIs

> Estes exemplos mostram exatamente quais campos existem em cada API.
> A IA deve usar apenas os campos documentados aqui — nunca assumir campos extras.

### Cinemeta — Resposta de busca de filme

**Request:** `GET https://v3-cinemeta.strem.io/catalog/movie/top/search=inception.json`

```json
{
  "metas": [
    {
      "id": "tt1375666",
      "type": "movie",
      "name": "Inception",
      "poster": "https://images.metahub.space/poster/medium/tt1375666/img",
      "year": "2010",
      "imdbRating": "8.8",
      "genres": ["Action", "Adventure", "Sci-Fi"],
      "director": ["Christopher Nolan"],
      "cast": ["Leonardo DiCaprio", "Joseph Gordon-Levitt", "Elliot Page"],
      "description": "A thief who steals corporate secrets through the use of dream-sharing technology...",
      "runtime": "148 min",
      "released": "2010-07-16T00:00:00.000Z",
      "trailerStreams": []
    }
  ]
}
```

**Campos obrigatórios (sempre presentes):** `id`, `type`, `name`

**Campos opcionais (podem estar ausentes — sempre usar `.get()`):**
`year`, `imdbRating`, `director`, `cast`, `genres`, `description`, `runtime`, `released`

---

### Cinemeta — Resposta de busca de série

**Request:** `GET https://v3-cinemeta.strem.io/catalog/series/top/search=breaking+bad.json`

```json
{
  "metas": [
    {
      "id": "tt0903747",
      "type": "series",
      "name": "Breaking Bad",
      "poster": "https://images.metahub.space/poster/medium/tt0903747/img",
      "year": "2008",
      "imdbRating": "9.5",
      "genres": ["Crime", "Drama", "Thriller"],
      "director": [],
      "cast": ["Bryan Cranston", "Aaron Paul"],
      "description": "A chemistry teacher diagnosed with inoperable lung cancer...",
      "runtime": "49 min"
    }
  ]
}
```

> ⚠️ Para séries, o campo `director` geralmente vem **vazio** (`[]`). Use `cast[0]` como fallback para o label do botão.

---

### Torrentio — Resposta de streams para filme

**Request:** `GET https://torrentio.strem.fun/stream/movie/tt1375666.json`

```json
{
  "streams": [
    {
      "name": "Torrentio\n🇧🇷 PT",
      "title": "Inception.2010.1080p.BluRay.x264\n👥 500  💾 8.7 GB  ⚙️ YTS",
      "infoHash": "08ada5a7a6183aae1e09d831df6748d566095a10",
      "fileIdx": 0,
      "sources": [
        "tracker:https://announce.example.com",
        "dht:08ada5a7a6183aae1e09d831df6748d566095a10"
      ],
      "behaviorHints": {
        "filename": "Inception.2010.1080p.BluRay.x264.mkv",
        "videoSize": 9341722624
      }
    },
    {
      "name": "Torrentio",
      "title": "Inception.2010.720p.WEBRip.x264\n👥 120  💾 2.1 GB  ⚙️ YIFY",
      "infoHash": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
      "fileIdx": 0,
      "behaviorHints": {
        "filename": "Inception.2010.720p.WEBRip.x264.mp4",
        "videoSize": 2254857830
      }
    },
    {
      "name": "HTTP",
      "title": "Inception 1080p",
      "url": "https://example-hoster.com/file/abc123.mkv",
      "behaviorHints": {
        "filename": "inception_1080p.mkv"
      }
    }
  ]
}
```

**Como extrair o magnet:**
```python
# infoHash presente → montar magnet
magnet = f"magnet:?xt=urn:btih:{stream['infoHash']}&dn={stream.get('name','')}"

# infoHash ausente → usar URL direta (stream HTTP, não torrent)
url = stream.get("url", "")
```

**Como extrair tamanho real:**
```python
# Forma 1: campo direto (mais preciso, em bytes)
size_bytes = stream.get("behaviorHints", {}).get("videoSize")

# Forma 2: parse do campo title (fallback)
# O title contém "💾 8.7 GB" ou "💾 2.1 GB"
import re
m = re.search(r"(\d+(?:\.\d+)?)\s*(GB|MB)", stream.get("title", ""), re.IGNORECASE)
```

**Como extrair qualidade:**
```python
# Combinar name + title + filename para detectar resolução
text = (stream.get("name","") + stream.get("title","") +
        stream.get("behaviorHints",{}).get("filename","")).lower()

for q in ["2160p","4k","1080p","720p","480p","360p"]:
    if q in text:
        return q
return "unknown"
```

---

### Torrentio — Resposta de streams para série

**Request:** `GET https://torrentio.strem.fun/stream/series/tt0903747:1:1.json`
_(Breaking Bad, Temporada 1, Episódio 1)_

```json
{
  "streams": [
    {
      "name": "Torrentio\n🇧🇷 PT",
      "title": "Breaking.Bad.S01E01.1080p.BluRay\n👥 88  💾 4.2 GB  ⚙️ YIFY",
      "infoHash": "dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c",
      "fileIdx": 1,
      "behaviorHints": {
        "filename": "Breaking.Bad.S01E01.Pilot.1080p.mkv",
        "videoSize": 4509715660
      }
    }
  ]
}
```

> ⚠️ Para séries, o campo `fileIdx` indica qual arquivo dentro do torrent é o episódio correto.
> Passar para o aria2c via `--select-file={fileIdx+1}` (aria2 usa índice 1-based).

---

## 🔲 Casos de Borda e Comportamento Esperado

> Esta seção define o comportamento correto para cada situação anormal.
> A IA deve implementar **exatamente** este comportamento ao gerar ou modificar o código.

### API e Rede

| Situação | Campo afetado | Comportamento esperado |
|---|---|---|
| Cinemeta retorna `metas: []` | Busca vazia | Mensagem: "😕 Nenhum resultado. Tente buscar em inglês." |
| Cinemeta timeout (>15s) | Qualquer busca | Mensagem: "⏳ Serviço lento, tente novamente em instantes." |
| Torrentio retorna `streams: []` | Seleção de stream | Mensagem: "😕 Sem streams disponíveis agora. Tente mais tarde." |
| Torrentio timeout (>20s) | Busca de streams | Mensagem: "⏳ Torrentio não respondeu. Tente novamente." |
| `infoHash` ausente E `url` ausente | Stream sem link | Ignorar esse stream — não exibir no teclado |
| `director` ausente ou `[]` | Label do botão | Usar `cast[0]` como fallback; se também vazio, omitir campo |
| `imdbRating` ausente | Label do botão | Omitir `⭐` do label silenciosamente |
| `year` ausente | Label do botão | Omitir o ano silenciosamente |
| `behaviorHints.videoSize` ausente | Tamanho do arquivo | Tentar parse do `title`; se falhar, exibir "? GB" |

### Download e Arquivos

| Situação | Comportamento esperado |
|---|---|
| `aria2c` não encontrado no PATH | Mensagem clara: "❌ aria2c não instalado. Rode: `sudo apt install aria2`" |
| Torrent sem seeders (0 peers por 5 min) | Cancelar, avisar: "⚠️ Torrent sem seeders. Tente outro stream." |
| Download completo mas nenhum `.mkv/.mp4/.avi` encontrado | Avisar: "❌ Arquivo de vídeo não encontrado após download." |
| Múltiplos arquivos de vídeo no diretório (pack de episódios) | Pegar o **maior** arquivo por `file.stat().st_size` |
| Arquivo `.rar` no diretório (torrent compactado) | Avisar: "⚠️ Torrent veio compactado (.rar). Tente outro stream." |
| Disco cheio durante download | Capturar `OSError`, avisar: "💾 Disco cheio! Libere espaço e tente novamente." |
| Arquivo > 2 GB (limite Bot API) | Avisar tamanho + caminho local; NÃO tentar enviar (vai falhar) |
| Download interrompido (bot reiniciado) | Ao receber pedido do mesmo conteúdo, aria2c com `--continue=true` retoma |

### Cache e Banco de Dados

| Situação | Comportamento esperado |
|---|---|
| `tg_file_id` no DB mas arquivo expirado no Telegram | Capturar exceção `BadRequest`, limpar `tg_file_id`, reenviar do arquivo local |
| `file_path` no DB mas arquivo deletado do disco | Limpar entrada do DB, refazer download normalmente |
| SQLite corrompido | Log de erro + recriar banco via `init_db()` |
| Dois usuários pedem o mesmo conteúdo simultaneamente | Segundo usuário recebe: "⏳ Este conteúdo já está sendo baixado. Você será notificado quando terminar." |

### Telegram e Usuários

| Situação | Comportamento esperado |
|---|---|
| Usuário não autorizado | "⛔ Acesso não autorizado." — sem mais detalhes |
| `callback_data` corrompido (JSON inválido) | Capturar `json.JSONDecodeError`, responder "❌ Erro interno. Tente a busca novamente." |
| Mensagem de callback muito antiga (>48h) | Telegram lança `BadRequest: query is too old` — capturar e ignorar silenciosamente |
| Upload do vídeo falha por timeout | Tentar 1 re-envio; se falhar de novo, avisar: "❌ Falha no envio. Arquivo salvo em: `{path}`" |
| Bot offline durante download agendado | Ao reiniciar, verificar tabela `downloads` com status `downloading` e remarcar como `failed` |

---

