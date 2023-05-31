### Info utili

La guida agli utilizzatori è nella [wiki](https://github.com/zeroone2numeral2/bbr-staff-bot/wiki) di questa repository, la lista delle cose da fare è nelle [issues](https://github.com/zeroone2numeral2/bbr-staff-bot/issues)

### Installazione

E' necessario avere Python 3.6+ installato sulla propria macchina.  

Per eseguire il bot:

```bash
# 1. installare le librerie utilizzate dal bot
pip install -r requirements.txt

# 2. creare una copia del file di configurazione di esempio e rinominarla in 'config.toml'
cp config.example.toml config.toml

# 3. modificare i valori delle variabili in 'config.toml' così come descritto nei commenti del file

# 4. avviare il processo
python main.py
```

Dopo ogni pull/sync, è necessario aggiornare la struttra del database all'ultima versione disponibile con:

```bash
alembic upgrade head
```
