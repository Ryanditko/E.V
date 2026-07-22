# Deploy da E.V. — Oracle Cloud (24/7)

Rodar a E.V. numa VM Always Free da Oracle, como serviço que liga sozinho.

## 1. Criar a VM (no console da Oracle)

- **Compute → Instances → Create Instance**
- Imagem: **Ubuntu 22.04** (ou Oracle Linux)
- Shape: **VM.Standard.A1.Flex** (ARM, Always Free) ou, se faltar capacidade,
  **VM.Standard.E2.1.Micro** (AMD, 1GB — suficiente).
- **Salve a chave SSH privada** que ele oferece pra baixar.
- Após criar, anote o **IP público** da instância.

## 2. Abrir a porta? Não precisa

O bot usa *long polling* (ele conecta no Telegram, ninguém conecta nele).
Não é necessário abrir portas de entrada.

## 3. Acessar a VM por SSH (do seu Mac)

```bash
chmod 400 ~/Downloads/sua-chave.key
ssh -i ~/Downloads/sua-chave.key ubuntu@SEU_IP_PUBLICO   # Oracle Linux: opc@
```

## 4. Clonar o código e configurar

```bash
sudo apt-get update -y && sudo apt-get install -y git   # se faltar git
git clone https://github.com/SEU_USUARIO/ev.git
cd ev
```

Crie o `.env` com as chaves (copie do seu Mac — veja abaixo) e rode:

```bash
bash deploy/setup_vm.sh
```

### Copiar o .env do Mac pra VM (rode NO SEU MAC)

```bash
scp -i ~/Downloads/sua-chave.key ~/ev/.env ubuntu@SEU_IP_PUBLICO:~/ev/.env
```

## 5. Pronto

A E.V. roda como serviço `ev`, liga no boot e reinicia se cair.

```bash
sudo systemctl status ev        # status
sudo journalctl -u ev -f        # logs ao vivo
```

## Atualizar depois

```bash
cd ~/ev && git pull && sudo systemctl restart ev
```
