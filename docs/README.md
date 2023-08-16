# Documentazione

Spiegone su come funziona il bot: cosa può fare, come lo fa, come utilizzarlo da admin ed utente

Le funzionalità principali del bot sono le seguenti:
- permettere agli utenti che non fanno già parte di flytek di richiedere di essere aggiunti
- per chi fa già parte del gruppo, mettersi in contatto con lo staff

Partiamo dalla funzionalità più semplice da spiegare, ovvero come funziona la comunicazione tra mebri di flytek e gruppo staff.



## Parlare con lo staff

Il bot permette a chiunque faccia parte di flytek (gruppo, non canale) di comunicare con lo staff inviando i messaggi che vuole che vengano recapitati allo staff direttamente nella chat con il bot.  
Questi messaggi vengono inoltrati nella chat che è stata impostata come "chat staff" (più info sulla gestione delle chat in seguito). I membri di questa chat potranno rispondere anonimamente ai messaggi ricevuti dagli utenti semplicemente rispondendo al messaggio dell'utente inoltrato nel gruppo.  

Il bot risponderà ad ogni messaggio inoltrato allo staff avvisando l'utente che effettivamente il messaggio è stato inoltrato (questo messaggio può essere disabilitato da `/settings`, più info su questo comando in seguito).

Gli utenti possono decidere di revocare un proprio messaggio inviato allo staff rispondendogli col comando `/revoke` oppure `/del`. Allo stesso modo, i membri della chat staff possono revocare un qualsiasi loro messaggio (anche inviato da un altro membro della chat staff).

Se si modifica un messaggio nella chat staff che è stato inviato come risposta ad un utente, anche il messaggio nella chat tra il bot e l'utente viene modificato di conseguenza (vale solo per i messaggi di testo, non per i media).  

Se si vuole rispondere ad un messaggio di un utente inviato dal bot nella chat staff **senza** che questa risposta venga inviata all'utente, basta iniziare il messaggio con un punto (".") (vale anche per i media, in questo caso il punto va messo nella didascalia). È possibile poi modificare il testo del messaggio.  

È anche possibile rispondere ad un messaggio di un altro admin facendo in modo che anche questa risposta venga inviata all'utente, iniziando il proprio messaggio con "++".

## Chiedere di essere aggiunti