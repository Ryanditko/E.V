# Deploy E.V. — Oracle Cloud (24/7)

Run E.V. on an Oracle Always Free VM, as a service that starts on its own.

## 1. Create the VM (Oracle console)

- **Compute → Instances → Create Instance**
- Image: **Ubuntu 22.04** (or Oracle Linux)
- Shape: **VM.Standard.A1.Flex** (ARM, Always Free) or, if capacity is missing,
  **VM.Standard.E2.1.Micro** (AMD, 1GB — enough).
- **Save the private SSH key** it offers to download.
- After creation, note the **public IP**.

## 2. Open a port? Not needed

The bot uses *long polling* (it connects to Telegram; nobody connects to it).
No inbound ports required.

## 3. SSH into the VM (from your Mac)

```bash
chmod 400 ~/Downloads/your-key.key
ssh -i ~/Downloads/your-key.key ubuntu@YOUR_PUBLIC_IP   # Oracle Linux: opc@
```

## 4. Clone the code and configure

```bash
sudo apt-get update -y && sudo apt-get install -y git   # if git is missing
git clone https://github.com/Ryanditko/E.V.git ev
cd ev
```

Create the `.env` with your keys (copy it from your Mac — see below) and run:

```bash
bash deploy/setup_vm.sh
```

### Copy the .env from your Mac to the VM (run ON YOUR MAC)

```bash
scp -i ~/Downloads/your-key.key ~/ev/.env ubuntu@YOUR_PUBLIC_IP:~/ev/.env
```

## 5. Done

E.V. runs as the `ev` service, starts on boot, and restarts on crash.

```bash
sudo systemctl status ev        # status
sudo journalctl -u ev -f        # live logs
```

## Update later

```bash
cd ~/ev && git pull && sudo systemctl restart ev
```
