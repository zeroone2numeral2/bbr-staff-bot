select
	u.name,
	cmg.user_id,
	cmg.chat_id,
	cmg.title as gruppo,
	cmg.status,
	cmg.created_on,
	cmg.updated_on,
	cmc.title as canale,
	cmc.status,
	cmc.has_been_member as has_been_member,
	cmc.created_on,
	cmc.updated_on
from (
		select cm1.*, c1.title
		from chat_members as cm1
			inner join chats as c1
				on cm1.chat_id = c1.chat_id
				and c1.is_users_chat = 1
		where 1=1
			and cm1.status in ('member', 'restricted')--, 'administrator', 'owner')
	) as cmg
	left join (
		select cm2.*, c2.title
		from chat_members as cm2
			inner join chats as c2
				on cm2.chat_id = c2.chat_id
				and c2.is_events_chat = 1
		where 1=1
			and cm2.status in ('member', 'restricted', 'administrator', 'owner')
	) as cmc
		on cmg.user_id = cmc.user_id
	left join users as u
		on cmg.user_id = u.user_id
where 1=1
	and ( -- membri gruppo non nel canale
		cmc.user_id is null
		or cmc.status not in ('member', 'restricted', 'administrator', 'owner')
	)
order by cmg.created_on;
