## comandi superadmin
### gestione approvatori

Gli approvatori sono gli utenti a cui è permesso gestire le richieste provenienti dagli utenti. Devono essere configurati manualmente da un superadmin

- `/approver` in un gruppo risposta ad un utente: abilita (o disabilita) un utente alla gestione delle richieste
- `/adminsapprovers` in un gruppo: tutti gli admin in quel gruppo saranno abilitati alla gestione delle richieste degli utenti
- `/approverslist` (gruppo o chat privata): elenca tutti gli utenti che sono abilitati alla gestione delle richieste
- `/resetapprovers` (gruppo o chat privata): resetta l'elenco degli utenti abilitati alla gestione delle richieste

### impostare le chat in cui il bot invia messaggi

Il bot funziona gestendo una serie di chat diverse:
- **chat utenti**: è la chat in cui vengono aggiunti gli utenti
- **chat staff**: è la chat dove verranno inviati:
  - i messaggi di notifica quando un utente che non è nel gruppo utenti chiede di essere aggiunto
  - i messaggi scritti dagli utenti che fanno già parte del gruppo e che vogliono comunicare con lo staff
- **chat log**: è la chat (idealmente un canale) in cui vengono inviati tutti i dati legati alle richieste degli utenti. Ovvero:
  - notifica di una nuova richiesta
  - allegati alle richieste degli utenti (foto/video/vocali, messaggi di presentazione)
  - notifica di un'azione da parte di un admin (richiesta accettata/rifiutata)
  - notifica quando un utente entra nel gruppo utenti senza aver prima effettuato il processo di approvazione
- **chat eventi**: canale in cui vengono inviati eventi e fly

comandi per impostare queste chat:
- `/suc` (in un gruppo): imposta il gruppo come chat degli utenti (gruppo flytek). Il bot dovrà obbligatoriamente essere admin (per sapere chi fa parte del gruppo) ed avere il permesso di invitare utenti (per generare i link di invito)
- `/ssc` (in un gruppo): imposta il gruppo come chat dello staff
- `/sec` (in privato, in risposta ad un messaggio inoltrato da un canale): imposta quel canale come canale degli eventi, in cui vengono postati gli eventi

### comandi approvatori

Gli approvatori sono gli utenti abilitati alla gestione delle richieste degli utenti.  
I superadmin possono aggiungere o rimuovere un utente dall'elenco degli approvatori con i comandi elencati sopra

- `/reset [user id, anche con hashtag]`: permetti all'utente di richiedere nuovamente l'accesso alla chat, anche se è stato rifiutato in precedenza
