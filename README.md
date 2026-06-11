# 🎬 Stremio Telegram Bot

> Um bot para Telegram desenvolvido em **Python** que busca filmes e séries via **Cinemeta**, obtém streams do **Torrentio**, realiza downloads com **aria2c**, comprime vídeos utilizando **ffmpeg** e envia o conteúdo diretamente pelo Telegram.
>
> O projeto utiliza **SQLite** para cache local e reaproveita `tg_file_id` sempre que possível para otimizar o envio.

---

> [!WARNING]
>
> ## ⚠️ Projeto Pausado
>
> Este projeto está **temporariamente pausado** devido a alterações na API utilizada, que inviabilizaram seu funcionamento.
>
> Estou avaliando alternativas para substituir essa dependência e, caso uma solução viável seja encontrada, o desenvolvimento será retomado.
>
> Enquanto isso, o repositório permanecerá disponível para fins de estudo e consulta.

---

# ✨ Recursos

* 🔎 Busca automática de filmes e séries
* 📺 Integração com Cinemeta e Torrentio
* ⬇️ Downloads via `aria2c`
* 📝 Detecção automática de legendas (`.srt` e `.ass`)
* 🎞️ Compressão automática de arquivos grandes com `ffmpeg`
* 📤 Envio direto para o Telegram
* 💾 Cache em SQLite
* ♻️ Reutilização de `tg_file_id`
* 🔒 Controle para impedir downloads duplicados
* 📋 Sistema de logs com rotação automática

---

# 🚀 Instalação

## Linux (Debian/Ubuntu)

### Pré-requisitos

* Python 3.11+
* aria2
* ffmpeg

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip aria2 ffmpeg
```

Configure o projeto:

```bash
cd /caminho/para/o/projeto

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
nano .env
```

Crie as pastas necessárias e execute:

```bash
mkdir -p downloads cache_db logs

source venv/bin/activate
python bot.py
```

---

## Windows

Crie e ative um ambiente virtual:

```powershell
cd C:\caminho\para\projeto

python -m venv venv

.\venv\Scripts\Activate.ps1

pip install -r requirements.txt

copy .env.example .env
```

Verifique as dependências:

```powershell
aria2c --version
ffmpeg -version
python --version
```

---

# ⚙️ Funcionamento

## 🔍 Busca

Você pode utilizar:

* `/start`
* `/buscar <título>`
* Ou simplesmente enviar o nome do filme ou série.

O bot retorna informações como:

* Título
* Ano
* Diretor/elenco
* Nota
* Streams disponíveis

---

## 📺 Séries

Ao selecionar uma série, o bot solicita:

1. Temporada
2. Episódio

Após a escolha, inicia o download.

---

## ⬇️ Downloads

* Utiliza `aria2c`
* Apenas **um download por usuário** é permitido simultaneamente
* O mesmo conteúdo não pode ser baixado duas vezes ao mesmo tempo graças a um sistema de bloqueio interno

---

# 📝 Legendas

O bot procura automaticamente arquivos:

* `.srt`
* `.ass`

A prioridade é definida por:

```text
SUB_LANG=pt-br,pt,en
```

Quando uma legenda compatível é encontrada:

* ela é renomeada para corresponder ao vídeo;
* é enviada automaticamente junto com o arquivo.

Caso contrário, o usuário pode escolher manualmente uma legenda disponível.

---

# 🎞️ Compressão

Arquivos maiores que **2 GB** entram automaticamente na fila de compressão.

---

# 🧹 Limpeza

O comando:

```text
/limpar [dias]
```

Remove:

* entradas antigas do cache;
* arquivos associados;
* cópias temporárias de legendas (quando permitido).

Caso nenhum parâmetro seja informado, o padrão é **30 dias**.

---

# 📋 Comandos Disponíveis

| Comando            | Descrição                    |
| ------------------ | ---------------------------- |
| `/start`           | Exibe ajuda                  |
| `/buscar <título>` | Busca filmes ou séries       |
| `/cache`           | Lista itens salvos no SQLite |
| `/status`          | Exibe uso de disco e cache   |
| `/limpar [dias]`   | Remove arquivos antigos      |

Também é possível pesquisar enviando apenas o nome do conteúdo.

---

# 🗂️ Estrutura do Banco

O cache utiliza SQLite (`DB_PATH`) e possui principalmente as tabelas:

* `cache`
* `downloads`

---

# 🔧 Principais Variáveis de Ambiente

| Variável             | Descrição                        |
| -------------------- | -------------------------------- |
| `BOT_TOKEN`          | Token do bot                     |
| `ALLOWED_USERS`      | IDs autorizados                  |
| `DOWNLOAD_DIR`       | Diretório dos downloads          |
| `DB_PATH`            | Banco SQLite                     |
| `DEFAULT_QUALITY`    | Qualidade preferida              |
| `SUB_LANG`           | Ordem de prioridade das legendas |
| `KEEP_SUBTITLE_COPY` | Mantém cópia da legenda          |
| `LOG_MAX_BYTES`      | Tamanho máximo do log            |
| `LOG_BACKUP_COUNT`   | Número de backups                |

> Consulte `.env.example` para a lista completa.

---

# 🛠️ Solução de Problemas

| Problema                    | Possível solução                        |
| --------------------------- | --------------------------------------- |
| `aria2c: command not found` | Instale `aria2`                         |
| `ffmpeg` não encontrado     | Instale `ffmpeg`                        |
| Nenhum resultado encontrado | Pesquise pelo título em inglês          |
| Download travado            | Escolha outro stream                    |
| Bot não inicia              | Verifique `BOT_TOKEN` e `ALLOWED_USERS` |
| Legenda incorreta           | Revise `SUB_LANG`                       |
| Vídeo sem legenda           | Consulte `logs/bot.log`                 |
| Compressão insuficiente     | Verifique o caminho informado pelo bot  |

---

# 📝 Logs

Os logs são armazenados em:

```text
logs/bot.log
```

A rotação é configurável por meio de:

* `LOG_MAX_BYTES`
* `LOG_BACKUP_COUNT`

---

# 📌 Observações

* O bot foi projetado para uso doméstico e listas restritas de usuários.
* O limite prático de envio pela Bot API é de aproximadamente **2 GB**.
* Caso um `tg_file_id` expire, o bot tenta reenviar o arquivo utilizando a cópia local.
* O gerenciamento de legendas pode ser totalmente automático ou manual, dependendo da configuração escolhida.

---

<div align="center">

**Desenvolvido em Python para automatizar downloads e envio de "mídia" no Telegram.**

</div>
