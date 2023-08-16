# Documentazione

Spiegone su come funziona il bot: cosa può fare, come lo fa, come utilizzarlo da admin ed utente

Le funzionalità principali del bot sono le seguenti:
- permettere agli utenti che non fanno già parte di flytek di richiedere di essere aggiunti
- per chi fa già parte del gruppo, mettersi in contatto con lo staff

Partiamo dalla funzionalità più semplice da spiegare, ovvero come funziona la comunicazione tra mebri di flytek e gruppo staff.



## Parlare con lo staff

Il bot permette a chiunque faccia parte di flytek (gruppo, non canale) di comunicare con lo staff inviando i messaggi che vuole che vengano recapitati allo staff direttamente nella chat con il bot.  
Questi messaggi vengono inoltrati nella chat che è stata impostata come "chat staff" (più info sulla gestione delle chat in seguito). I membri di questa chat potranno rispondere anonimamente ai messaggi ricevuti dagli utenti semplicemente rispondendo al messaggio dell'utente inoltrato nel gruppo.  

Il bot risponderà a ogni messaggio inoltrato allo staff avvisando l'utente che effettivamente il messaggio è stato inoltrato (questo messaggio può essere disabilitato da `/settings`, più info su questo comando in seguito).

Gli utenti possono decidere di revocare un proprio messaggio inviato allo staff rispondendogli col comando `/revoke` oppure `/del`. Allo stesso modo, i membri della chat staff possono revocare un qualsiasi loro messaggio (anche inviato da un altro membro della chat staff).

Se si modifica un messaggio nella chat staff che è stato inviato come risposta ad un utente, anche il messaggio nella chat tra il bot e l'utente viene modificato di conseguenza (vale solo per i messaggi di testo, non per i media).  

Se si vuole rispondere ad un messaggio di un utente inviato dal bot nella chat staff **senza** che questa risposta venga inviata all'utente, basta iniziare il messaggio con un punto (".") (vale anche per i media, in questo caso il punto va messo nella didascalia). È possibile poi modificare il testo del messaggio.  

È anche possibile rispondere ad un messaggio di un altro admin facendo in modo che anche questa risposta venga inviata all'utente, iniziando il proprio messaggio con "++".

Molte delle risposte predefinite del bot, comunque, sono in inglese perchè questa parte del codice è in comune con BBR, che è un gruppo internazionale e quindi le risposte sono in inglese. Questa cosa verrà sistemata più avanti.

## Chiedere di essere aggiunti

Prima di spiegare come funziona questa cosa del richiedere l'approvazione, breve premessa su come il bot gestisce le chat necessarie al suo funzionamento. Queste chat sono 5:
- **chat "utenti"**: il gruppo a cui la gente viene aggiunta, dove si trovano tutti gli utenti (ovvero flytek/radar23, d'ora in avanti per comodità verrà chiamata "chat flytek")
- **chat staff**: la chat dello staff
- **chat approvatori**: la chat da cui gestire le richieste degli utenti che vogliono essere aggiunti alla chat flytek
- **canale eventi**: il canale in cui vengono postati i fly/comunicati
- **canale log**: canale in cui il bot posta gli eventi rilevanti riguardo le richieste degli utenti che vogliono farsi aggiungere

Per dire al bot quali sono queste chat, è sufficiente usare il comando `/setchat` (può usarlo solo vlad perchè per ora è l'unico "superadmin" configurato). Per dire al bot che un gruppo è il gruppo staff, ad esempio, basta mandare nel gruppo `/setchat staff`. Allo stesso modo, per configurare gli altri due tipi di gruppo, si usa `/setchat users` e `/setchat approvers`. Per configurare i due canali, invece, bisogna inoltrare al bot (in privato) un messaggio dal canale che si vuole usare e rispondere a quel messaggio con `/setchat events` o `/setchat log`.

Una volta che queste chat sono state impostate, il bot è pronto a gestire le richieste provenienti dalla gente che vuole farsi aggiungere.

***

Quando il bot viene avviato (ovvero riceve il comando `/start`), se l'utente non fa parte del gruppo flytek verrà avviata la "procedura" (non mi viene in mente un termine decente) di verifica, per richiedere di essere aggiunti al gruppo.  
All'utente vengono richieste tre informaizoni, in quest'ordine:
1. username di altre persone che conosce all'interno del gruppo (skippabile)
2. link ai suoi social (skippabile)
3. uno o più messaggi di presentazione (**non** skippabile)

Ciò che vogliamo che l'utente invii all'ultimo step dipende da come formuliamo il messaggio che riceve dal bot; al momento viene semplicemente chiesto di boh, descriversi. Sta cosa va decisa. 
Comunque in questo step all'utente è permesso inviare qualsiasi cosa: uno o più messaggi di testo, vocali, videomessaggi, musica, gif, foto, video.

La richiesta viene annullata automaticamente se si verificano queste condizioni:
- trascorrono 20 minuti d'inattività
- l'utente non ha inviato alcun messaggio in cui si presenta

Se invece trascorrono i 20 minuti d'inattività e l'utente ha inviato almeno un messaggio di presentazione, il bot invierà in automatico la richiesta nella chat degli approvatori senza che l'utente la invii esplicitamente.

Una volta che la richiesta è stata inviata agli approvatori, all'utente viene richiesto di attenderne l'esito. La richiesta viene inviata nel canale di log e nel gruppo per le approvazioni, da cui sarà possibile accettare o rifiutare la richiesta. 
Il messaggio inviato in questo gruppo contiene solo le info fondamentali della richiesta - eventuali messaggi di presentazione ed allegati vengono solo inviati nel canale log, per mantenere la chat più snella possibile.

#### Accettare o rifiutare un utente

Per accettare o rifiutare un utente basta usare i tasti "accetta" e "rifiuta" sotto al messaggio inviato dal bot nel gruppo per le approvazioni. Solamente gli admin di questa chat hanno il permesso di usarli.

Se un utente viene rifiutato, il bot elimina la cronologia della chat con l'utente e invia una gif molto fica. Molto scenico.  
Gli utenti rifiutati non potranno usare il bot per parlare con lo staff, e non potranno avviare di nuovo la procedura per richiedere di essere aggiunti, a meno che non venga usato il comando `/reset` (vedi dopo).

Se un utente invece viene accettato, riceve dal bot un link d'invito **generato appositamente** per lui. 
Il link può essere usato da un solo utente, questo significa che una volta che l'utente lo usa per unirsi alla chat, nessuno potrà più farne uso. Inoltre, il messaggio che contiene il link non può essere inoltrato e il suo testo non può essere copiato.  
Non appena l'utente si unisce al gruppo, per sicurezza il link viene anche revocato e viene anche rimosso dal messaggio che l'utente ha ricevuto che gli comunicava che la sua richiesta è stata accettata. 
Queste precauzioni dovrebbero fare si che condividere il link per entrare sia pressochè impossibile.

Importante: per generare link d'invito, il bot deve essere admin nella chat flytek e avere il permesso di aggiunere utenti. 
Se non ha il permesso di farlo, agli utenti accettati viene inviato il link salvato in `/settings`.

Anche i comandi `/accetta` e `/rifiuta` possono essere usati per accettare o rifiutare una richiesta di un utente. 
Si utilizzano fornendo l'ID o l'hastag dell'utente:  `/accetta 1234567` oppure `/accetta #id1234567`.

Dopo che un utente è stato accettato, potrà utilizzare il bot per parlare con lo staff come descritto sopra. Cosa non possibile mentre una richiesta è pendente.

#### Resettare le richieste di un utente

È possibile resettare la richiesta (pendente o rifiutata) di un utente usando il comando `/reset` seguito dall'ID o l'hashtag identificativo di un utente, ad esempio: `/reset 1234567` oppure `/reset #id1234567` (l'hashtag si può trovare in un qualsiasi messaggio inviato da bot riguardo alle richieste di un determinato utente).  
L'utente potrà così provare a inviare una nuova richiesta, usando il comando `/start`. Viene anche unbannato dalla chat flytek, nel caso in cui fosse stato bannato.

***

Altre cose:
- gli utenti accettati ma che per qualsiasi motivo non si sono uniti alla chat flytek possono comunque usare il bot per parlare con lo staff
- il bot invia nel canale log un messaggio che notifica quando si unisce un membro tramite link d'invito che non è passato attraverso il processo di verifica, o ne ha uno pendente, o è stato rifiutato. Questa cosa non dovrebbe succedere ed è per questo che viene loggata

### Altri comandi staff

Per bannare qualcuno dall'utilizzare il bot si usa il comando `/ban` in risposta ad un messaggio dell'utente inoltrato nel gruppo staff. 
È possibile anche fornire una motivazione dopo il comando.  
`/shadowban` funziona allo stesso modo, ma agli utenti bannati non verrà comunicato che sono stati bannati quando usano il bot (per loro è come se il bot non funzionasse)
