select
	ar.user_id,
	cm.chat_id,
	u.first_name,
	u.last_name,
	u.username,
	--ar.status as request_status,
	ar.accepted_message_message_id,
	ar.invite_link,
	cm.status as membership,
	cm.has_been_member,
	ar.status_changed_on as approved_on,
	cm.updated_on as chat_member_updated_on
from application_requests as ar
	left join users as u
		on ar.user_id = u.user_id
	left join chat_members as cm
		on ar.user_id = cm.user_id
		-- left 
		and (cm.status not in ('creator', 'administrator', 'member', 'restricted') or cm.status is null)
where 1=1
	and ar.status = 1
	and ar.accepted_message_message_id is not null
	and cm.chat_id = (select chat_id from chats where is_users_chat = 1)
order by
	cm.updated_on;
	