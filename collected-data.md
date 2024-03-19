### Data this bot collects

- basic metadata (user id, name, username, bot/premium status) of the user it meets in groups and private chats
- users' first/last interaction's timestamps
- basic metadata (ids, timestamps, whether the message was revoked or not) of all messages received in private (so they can be revoked based on their datetime)
- basic metadata (id, title, username, forum status) of the chats this bot is added to
- membership status and permissions of the members of the group chats it moderates
- basic metadata (ids, timestamps, whether the message was revoked or not, ids of media files) of the messages exchanged during a user-staff conversation
- timestamps, text and medias from the comments posted in the channel (they are assumed to be info about the parties in the channel)
- all the data provided while filing a request to join the users' chat, and all related timestamps
- staff chat: the hashed version of all text messages larger than 60 bytes and the ids of medias (duplicates check) 
