# Bot do Supremo Tribunal de Meta City (STMC)

Bem-vindo(a) ao repositório do bot do **Setor Jurídico** da sua cidade de roleplay (FiveM). 

Este bot foi desenvolvido para automatizar e profissionalizar o Discord do seu tribunal. Ele gerencia todo o fluxo de **Atendimento (Tickets)**, **Registros de Advogados e Seguranças**, **Sistema de Advertências** e **Exoneração**, mantendo um padrão visual corporativo e um banco de dados local para que você não perca nenhum histórico.

Este guia foi escrito de forma simples, para que qualquer pessoa consiga colocar o bot online, mesmo sem experiência com programação ou servidores.

---

## 📋 Requisitos Antes de Começar

Para colocar este bot no ar 24/7 (ligado 24 horas por dia), você vai precisar de:
1. **Uma conta no Discord** (para gerenciar o servidor e criar o bot).
2. **Um computador com internet** (para configurar e testar).
3. **Uma conta na AWS (Amazon Web Services)** (para manter o bot hospedado de graça na nuvem). 

---

## 🤖 1. Criação do Bot no Discord Developer Portal

Antes de mexer no código, precisamos "registrar" o bot no Discord.

1. Acesse o [Discord Developer Portal](https://discord.com/developers/applications).
2. Clique no botão azul **New Application** no canto superior direito. Dê o nome de "Supremo Tribunal" (ou o que preferir) e concorde com os termos.
3. No menu à esquerda, clique em **Bot**.
4. Encontre o botão **Reset Token**, clique nele e copie a longa linha de texto que aparecer. **Este é o Token do seu bot. NUNCA o compartilhe com ninguém, pois ele dá controle total sobre o seu bot.**
5. Role a mesma página um pouco para baixo até achar a seção **Privileged Gateway Intents**.
   - Ligue a chave **Server Members Intent**.
   - Ligue a chave **Message Content Intent**.
   - *Importante:* Se essas chaves ficarem desligadas, o bot não vai conseguir ler mensagens ou reconhecer os cargos dos membros. Salve as alterações.
6. Vá no menu à esquerda em **OAuth2** > **URL Generator**.
7. Na caixa "Scopes", marque **bot** e **applications.commands**.
8. Na caixa "Bot Permissions", marque **Administrator** (Administrador).
9. Copie a URL gerada no fim da página, cole no seu navegador e convide o bot para o servidor do seu tribunal.

---

## ⚙️ 2. Configuração em 5 Minutos

O bot precisa saber onde ele está e quem manda nele. Fazemos isso através de um arquivo chamado `.env` (lê-se "ponto env").

### Passo a passo:
1. Na pasta deste projeto, você verá um arquivo chamado `.env.example`.
2. **Copie** este arquivo e cole na mesma pasta, renomeando a cópia exatamente para `.env` (só isso, sem "txt" no final).
3. Abra o seu novo arquivo `.env` no Bloco de Notas. Você verá várias variáveis com valores falsos de zeros. Troque cada zero pelo valor real do seu servidor.

### Checklist de Conferência do .env
- [ ] O token foi colado **sem aspas**? (Certo: `DISCORD_TOKEN=MTU...` | Errado: `DISCORD_TOKEN="MTU..."`)
- [ ] Os IDs têm só números? 
- [ ] O arquivo se chama exatamente `.env`? (Verifique se o Windows não ocultou a extensão e o chamou de `.env.txt`).

> **Como copiar IDs no Discord:** Vá em *Configurações do Usuário > Avançado > Ative o "Modo Desenvolvedor"*. A partir de agora, você pode clicar com o botão direito em qualquer canal, cargo ou servidor e escolher "Copiar ID".

### Tabela de Configurações (Preencha nesta ordem)

#### Obrigatórias (Se faltarem, o bot não liga)
| Variável | O que é? | Onde pegar? |
| :--- | :--- | :--- |
| `DISCORD_TOKEN` | A senha do seu bot. | Developer Portal > Bot > Reset Token. |
| `GUILD_IDS` | ID do seu Servidor. | Botão direito no ícone do servidor > Copiar ID. |
| `LOG_CHANNEL_ID` | Canal de texto onde ficam os logs dos tickets. | Botão direito no canal > Copiar ID. |
| `TICKET_CATEGORY_NOME_ID` | Categoria onde cairão os tickets de troca de nome. | Botão direito na categoria > Copiar ID. |
| `TICKET_CATEGORY_CERTIDAO_ID` | Categoria de tickets de certidão. | Botão direito na categoria > Copiar ID. |
| `TICKET_CATEGORY_PORTE_ID` | Categoria de tickets de porte de arma. | Botão direito na categoria > Copiar ID. |
| `TICKET_CATEGORY_PROCESSO_ID` | Categoria de tickets de processos. | Botão direito na categoria > Copiar ID. |
| `TICKET_CATEGORY_CNPJ_ID` | Categoria de tickets de CNPJ. | Botão direito na categoria > Copiar ID. |
| `TICKET_CATEGORY_PATENTE_ID` | Categoria de tickets de patentes. | Botão direito na categoria > Copiar ID. |
| `ADMIN_ROLE_ID` | Cargo de chefia suprema que controla tudo. | Configurações do servidor > Cargos > Copiar ID. |
| `RECRUTADOR_ROLE_ID` | Cargo que pode aprovar/recusar advogados. | Configurações do servidor > Cargos > Copiar ID. |
| `ADV_1_ID`, `ADV_2_ID`, `ADV_3_ID` | Cargos dos advogados (usado nas advertências). | Configurações do servidor > Cargos > Copiar ID. |
| `CARGO_ESTAGIARIO_ID` | Cargo(s) de entrada na advocacia. | Config. do servidor > Cargos > Copiar ID. |
| `CARGO_SEGURANÇA_ID` | Cargo(s) da equipe de segurança. | Config. do servidor > Cargos > Copiar ID. |

*(Nota: O arquivo .env.example também possui variáveis opcionais. Elas estão explicadas dentro do próprio arquivo!)*

---

## 💻 3. Execução Local (Testando no seu PC)

Se quiser ver se tudo está funcionando antes de mandar para a internet, você pode rodar o bot no seu próprio computador.

**Opção A: Com Docker (Recomendado)**
Se você tiver o Docker Desktop instalado:
1. Abra o terminal (Prompt de Comando ou PowerShell) na pasta do projeto.
2. Digite: `docker compose up -d --build` e aperte Enter.
3. Para ver o que o bot está fazendo (logs), digite: `docker compose logs -f`.
4. Para desligar o bot, digite: `docker compose down`.

**Opção B: Sem Docker (Para quem tem Python instalado)**
1. Certifique-se de ter o Python 3.13 instalado.
2. No terminal, digite: `python -m venv venv` (para criar um ambiente virtual).
3. Ative-o:
   - No Windows: `venv\Scripts\activate`
   - No Mac/Linux: `source venv/bin/activate`
4. Instale as dependências: `pip install -r requirements.txt`
5. Rode o bot: `python main.py`

---

## ☁️ 4. Deploy na AWS (Deixando 24 horas online)

Para que o bot não desligue quando você fechar seu computador, vamos usar a **AWS (Amazon Web Services)**. A AWS oferece uma máquina gratuita por 1 ano (o chamado *Free Tier* ou Nível Gratuito).
*Aviso:* Acompanhe seu uso na AWS para não gerar custos se você exceder as horas do Nível Gratuito.

### Passo 4.1: Criar o Computador Virtual (Instância EC2)
1. Crie uma conta na [AWS](https://aws.amazon.com/pt/).
2. Busque por **EC2** na barra superior e clique.
3. Clique no botão laranja **Executar Instância** (Launch Instance).
4. Dê um nome (ex: `bot-stmc`).
5. Em **Imagens de SO (AMI)**, escolha **Ubuntu** (a primeira opção padrão).
6. Em **Tipo de Instância**, mantenha `t2.micro` (esta é a elegível para o nível gratuito).
7. Em **Par de chaves (login)**, clique em "Criar novo par de chaves". Dê um nome (ex: `chave-bot`), mantenha formato `.pem` e clique em Criar. O arquivo fará download. **Guarde esse arquivo em um local seguro, você não pode baixá-lo de novo!**
8. Na aba "Configurações de rede", marque apenas **Permitir tráfego SSH**. (Dica avançada: limite o IP de origem para "Meu IP" se sua internet não mudar sempre, para maior segurança).
9. Clique em **Executar Instância** no canto inferior direito.

### Passo 4.2: Conectar ao Computador Virtual
Abra seu terminal no computador onde salvou o arquivo `.pem` (geralmente a pasta Downloads).

**Se você usa Windows:**
O Windows é chato com a permissão do arquivo. Se você tiver erro de permissão ao tentar conectar, abra as propriedades do arquivo `.pem` > Segurança > Avançado > Desative a herança e remova todos os usuários, deixando apenas você com Controle Total.
Para conectar, veja o IP Público da sua instância na AWS e digite no terminal:
`ssh -i chave-bot.pem ubuntu@SEU_IP_PUBLICO_AQUI`

**Se você usa Mac ou Linux:**
`chmod 400 chave-bot.pem`
`ssh -i chave-bot.pem ubuntu@SEU_IP_PUBLICO_AQUI`

### Passo 4.3: Instalar o Docker na Máquina
Uma vez conectado na máquina preta (Ubuntu), cole os comandos abaixo, um por vez, apertando Enter:

1. Atualizar o sistema:
`sudo apt update && sudo apt upgrade -y`
2. Instalar o Docker:
`sudo apt install docker.io docker-compose-v2 git -y`
3. Permitir que o Ubuntu use o Docker sem precisar de senha:
`sudo usermod -aG docker ubuntu`
*(Para que isso tenha efeito, feche o terminal, abra de novo e reconecte no SSH).*

### Passo 4.4: Enviar o Bot e Ligar
1. Clone seu código do GitHub para a máquina:
`git clone LINK_DO_SEU_REPOSITORIO`
2. Entre na pasta clonada:
`cd NOME_DA_PASTA`
3. Crie o seu arquivo `.env` na máquina colando seus IDs:
`nano .env`
*(Isso abre um editor de texto no terminal. Cole o conteúdo do seu `.env` lá. Para salvar e sair, aperte `Ctrl + O`, `Enter`, e depois `Ctrl + X`).*
4. Ligue o bot!
`docker compose up -d --build`

Seu bot está online! A configuração `restart: unless-stopped` que criamos já garante que, se o computador da AWS reiniciar, o Docker religa o seu bot sozinho.

### Como atualizar o bot no futuro?
Se você mudar o código no GitHub e quiser atualizar na AWS, conecte via SSH, entre na pasta do bot e faça:
1. `git pull` (para puxar o código novo)
2. `docker compose up -d --build` (para recriar o bot com as atualizações).

---

## 🛑 5. Problemas Comuns

- **"O bot liga no terminal mas não fica verde (online) no Discord"**
  **Solução:** Seu Token está inválido ou você não colou inteiro. Abra o arquivo `.env` e veja se colou o Token exatamente como o Discord forneceu. Não deixe espaços antes nem depois do sinal de igual.
- **"O bot dá um erro dizendo 'Privileged Intents are not explicitly enabled'"**
  **Solução:** Volte no Passo 1, acesse o Portal de Desenvolvedor do Discord e ligue as opções *Message Content Intent* e *Server Members Intent*.
- **"O bot liga, mas os comandos de Slash (/) não aparecem no servidor"**
  **Solução:** O Discord demora até 1 hora para registrar comandos novos globalmente, MAS, se você preencheu a variável `GUILD_IDS` corretamente, eles aparecem quase de imediato. Confirme se o ID do servidor está correto.
- **"Erro: ValueError: invalid literal for int() with base 10"**
  **Solução:** Você colocou letras ou espaços onde o código só aceita números. Abra o `.env`, confira todas as variáveis e apague espaços em branco perdidos ou comentários colados na mesma linha sem o jogo-da-velha `#`.
- **"ConnectionRefusedError" ao conectar na AWS**
  **Solução:** A máquina ainda está ligando (espere 1 minuto) ou você não permitiu o tráfego SSH na porta 22 durante a criação. Vá no painel da AWS, encontre o "Security Group" da instância e adicione uma regra de entrada (Inbound Rule) para SSH na porta 22.

---

## 📚 6. Guia de Comandos do Bot

O bot funciona exclusivamente por Slash Commands (aqueles que você digita `/` e o Discord sugere). Todos os comandos de configuração são protegidos e exigem o cargo de Administrador (ou similar).

| Comando | Para que serve | Quem pode usar | O que o bot faz |
| :--- | :--- | :--- | :--- |
| `/setup_tickets` | Cria a mensagem visual base (Painel) onde os jogadores abrirão os tickets de atendimento (CNPJ, Processos, etc). | Apenas Staff (Admin) | Envia um Embed bonito com um menu (*Select Menu*) no canal onde você digitou. |
| `/setup_registro` | Cria o painel inicial para os jogadores pedirem entrada na equipe como Advogado ou Segurança. | Apenas Staff (Admin) | Envia o painel com os botões "Registro de Advogados" e "Registro de Seguranças". |
| `/listar_registros` | Mostra uma lista de quem já foi aprovado nas funções do Tribunal. | Recrutadores e Admin | Responde apenas para quem chamou (*ephemeral*) com uma lista organizada dos membros e passaportes. |
| `/setup_advertencia` | Cria o painel que o Staff do tribunal usará para gerenciar e punir (advertir) advogados faltosos. | Apenas Staff (Admin) | Envia a mensagem permanente de advertências no canal. |
| `/setup_demissao` | Cria o painel final para Exoneração de membros. | Apenas Staff (Admin) | Envia o painel que, ao ser clicado, remove os cargos do membro e anuncia a saída. |

**Fluxo diário (Exemplo: Registro):**
1. O Administrador vai em um canal restrito e usa `/setup_registro`.
2. O jogador clica em "Registro de Advogados", preenche o formulário (passaporte, nome, telefone).
3. O bot avisa que foi enviado para aprovação e posta os dados do jogador em um canal privado de avaliação.
4. Um Recrutador avalia, clica em "Aceitar". O bot automaticamente muda o apelido (nick) do jogador no Discord, dá o cargo correspondente, manda uma mensagem na DM dele avisando da aprovação e loga o resultado!

---

## 📁 7. Estrutura do Projeto (Para Curiosos)

Caso você queira explorar como o bot funciona por dentro, esta é a organização:

- `main.py` - O "motor" principal. Onde o bot liga, sincroniza os comandos e carrega os módulos.
- `cogs/` - Cada arquivo aqui é um módulo (uma peça do robô). Tem a engrenagem de registro, a de advertência, a de tickets, etc.
- `config/settings.py` - Puxa os dados do seu arquivo `.env` para que o código possa usar.
- `database/` - Onde o banco de dados (SQLite) é criado e gerenciado. Mantém as tabelas para armazenar tudo.
- `utils/` - Ferramentas de apoio. Por exemplo, `ui.py` é responsável por criar os quadros coloridos (Embeds) que o bot posta.
- `Moldes/` - Pasta externa que guardava materiais da cidade. (Fica fora da execução real, então o bot ignora).

*Boas execuções no Supremo Tribunal de Meta City!*
