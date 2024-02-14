select c.*, u.name
from (
	select user_id, count(*) as msgs
	from private_chat_messages
	group by user_id
) as c
	left join users as u
		on c.user_id = u.user_id
order by c.msgs desc;
