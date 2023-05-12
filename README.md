## comandi superadmin
### gestione approvatori

Gli approvatori sono gli utenti a cui è permesso gestire le richieste provenienti dagli utenti. Devono essere configurati manualmente da un superadmin

- `/approver` in un gruppo e in risposta ad un utente: abilita (o disabilita) un utente alla gestione delle richieste
- `/adminsapprovers` in un gruppo: tutti gli admin in quel gruppo saranno abilitati alla gestione delle richieste degli utenti
- `/approverslist` (gruppo o chat privata): elenca tutti gli utenti che sono abilitati alla gestione delle richieste
- `/resetapprovers` (gruppo o chat privata): resetta l'elenco degli utenti abilitati alla gestione delle richieste

### impostare le chat in cui il bot invia messaggi

Il bot funziona gestendo una serie di chat diverse:
- **chat utenti**: è la chat in cui vengono aggiunti gli utenti
- **chat staff**: è la chat dove verranno inviati:
  - i messaggi di notifica quando un utente che non è nel gruppo utenti chiede di essere aggiunto. Per ogni richiesta viene inviato un solo messaggio nella chat dello staff, che viene modificato nel momento in cui la richiesta viene accettata/rifiutata da un approvatore. Tutto il resto viene inviato nella chat log, per evitare di creare chaos nella chat staff
  - i messaggi scritti dagli utenti che fanno già parte del gruppo e che vogliono comunicare con lo staff
- **chat log**: è la chat (idealmente un canale) in cui vengono inviati tutti i dati legati alle richieste degli utenti. In questa chat viene pubblicato un messaggio ogni volta che una richiesta viene aggiornata in qualche modo. I messaggi che vengono inviati qui sono:
  - la notifica di una nuova richiesta
  - gli allegati alle richieste degli utenti (foto/video/vocali, messaggi di presentazione)
  - la notifica di un'azione da parte di un admin (richiesta accettata/rifiutata)
  - la otifica di un utente che entra nel gruppo utenti senza aver prima effettuato il processo di approvazione
- **chat eventi**: canale in cui vengono inviati eventi e fly

comandi per impostare queste chat:
- `/setchat staff` o `/setchat users` (in un gruppo): imposta quel gruppo come chat staff oppure chat utenti
- `/setchat log` o `/setchat events` (in privato, in risposta ad un messaggio inoltrato da un canale): imposta quel canale come log oppure canale in cui vengono postati gli eventi

altri comandi:
- `/chats` (in privato o in un gruppo): restituisce l'elenco delle chat rilevanti

## comandi approvatori

Gli approvatori sono gli utenti abilitati alla gestione delle richieste degli utenti.  
I superadmin possono aggiungere o rimuovere un utente dall'elenco degli approvatori con i comandi elencati sopra

- `/reset [user id, anche con hashtag]`: permetti all'utente di richiedere nuovamente l'accesso alla chat, anche se è stato rifiutato in precedenza

## Comandi per admin chat staff/approvazione utenti

- `/ban [motivazione]` (chat staff, in risposta ad un messaggio inviato da un utente): banna l'utente, non potrà più utilizzare il bot. Quando l'utente invia un messaggio il bot lo informerà che è stato bannato
- `/shadownban [motivazione]` (chat staff, in risposta ad un messaggio inviato da un utente): come `/ban`, ma il bot non risponderà ai suoi messaggi dicendogli che è stato bannato
- `/unban` (chat staff, in risposta ad un messaggio inviato da un utente): si capisce dai
