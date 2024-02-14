select c.*, u.name
from (
	select staff_user_id as user_id, count(*) as msgs
	from admin_messages
	group by user_id
) as c
	left join users as u
		on c.user_id = u.user_id
order by c.msgs desc;
