# Serviço HTTPS de pareamento PH Pocket

Código WSGI completo, PKCE, sem Client Secret. Serviço pessoal para a sua placa, com uma chave de inscrição compartilhada apenas entre serviço e CYD. Sessões expiram em 5 minutos, têm segredo aleatório de 256 bits para o dispositivo, state aleatório, verifier PKCE e código de seis dígitos confirmado no celular. Poll/ACK exigem segredo do dispositivo. Browser nunca recebe refresh token. ACK apaga a sessão; sem ACK a expiração apaga na próxima requisição. Não há banco de tokens. Reiniciar o serviço invalida sessões em andamento. Use exatamente um worker e uma instância: armazenamento em RAM não funciona com múltiplos processos.

## Publicar no Render

1. Crie um repositório privado seu no GitHub e envie somente o conteúdo desta pasta `pairing-service` (app.py, requirements.txt, render.yaml, README.md). Não envie seu .env. Nenhum segredo do projeto é necessário no repositório.
2. No Render: New → Web Service → conecte o repositório. Runtime Python. Build Command: `pip install -r requirements.txt`.
3. Start Command:

```text
gunicorn app:application --workers 1 --threads 4 --bind 0.0.0.0:$PORT --timeout 30 --access-logfile /dev/null
```

4. Em Environment configure:
   - `PYTHON_VERSION`: `3.12.10`.
   - `SPOTIFY_CLIENT_ID`: o Client ID público do seu aplicativo.
   - `DEVICE_ENROLLMENT_KEY`: uma chave aleatória de 64 caracteres hexadecimais, gerada no seu PC com `py -3.12 -c "import secrets;print(secrets.token_hex(32))"`. Não use exemplos fixos.
5. Deploy. O serviço usa automaticamente `RENDER_EXTERNAL_URL`. Copie a URL realmente fornecida pelo Render. Se usar domínio próprio, configure `PUBLIC_BASE_URL` com sua origem HTTPS, sem barra final/caminho/porta.
6. Abra `https://SEU-ENDERECO-REAL/health`: precisa retornar `{"ready":true}`. SEU-ENDERECO-REAL é um marcador, não um domínio fornecido pelo projeto.
7. No Spotify Dashboard, cadastre exatamente a URL do serviço seguida de `/callback`. Exemplo de formato: `https://SEU-ENDERECO-REAL/callback`. Mantenha `http://127.0.0.1:8766/callback` se também quiser continuar usando USB. O callback novo precisa corresponder exatamente ao usado no serviço.

A hospedagem gratuita pode dormir e demorar para iniciar. Antes de gerar o QR, abra /health no celular e aguarde. Não há rotina para manter a instância artificialmente acordada. O serviço precisa estar disponível durante o pareamento; depois a placa renova e controla Spotify diretamente. Nenhum áudio passa por este serviço.

## Configurar o CYD (uma vez)

1. Instale o firmware **0.3.5** no perfil `bruce_cyd_2usb`.
2. No `.env` local, adicione:

```ini
PH_PAIR_URL=https://SEU-ENDERECO-REAL
PH_PAIR_KEY=SUA-CHAVE-GERADA
PH_USB_PORT=COM7
```

3. Libere o console no webflasher e execute `configurar-qr.cmd`. URL/chave são salvas na placa; o Client ID é configurado no serviço. Chave não aparece nos logs do assistente. Pode informar URL e chave interativamente se não preencher .env.
4. Com Wi-Fi e hora sincronizados: Ajustes → Conta Spotify → Conectar pelo QR.
5. Escaneie o QR, digite os seis dígitos da tela, autorize Spotify e aguarde a confirmação na placa. Não é um device code oficial do Spotify: é um código de confirmação do nosso pareamento.
6. Depois disso pode desligar o computador. USB continua disponível como alternativa. Restaurar a placa apaga URL/chave; desconectar Spotify apaga a sessão Spotify mas mantém a configuração do servidor para reconectar.

QR cancelado na placa deixa de ser consultado; o servidor descarta a sessão na expiração. Sessões com token podem ser consultadas novamente pelo mesmo segredo até ACK/expiração para tolerar perda de resposta. A entrega é idempotente; callback state é estritamente de uso único. Desconectar Spotify na placa não revoga a permissão no Dashboard da conta: use a página de aplicativos autorizados da conta para isso.

## Verificação

`python -m unittest discover -s ../tests -p 'test_*.py'` no projeto completo. Testes simulam API/token, expiração, state, PKCE, replay, PIN, capacidade, chave incorreta, entrega e ACK. Captura/varredura de QR, TLS Render ao vivo, publicação real, OAuth Spotify real e touch exigem validação externa. Não há Client Secret, senha de conta ou tokens em exemplos.

Fontes oficiais: https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow ; https://developer.spotify.com/documentation/web-api/concepts/redirect_uri ; https://render.com/docs/deploy-flask ; https://render.com/docs/free .
