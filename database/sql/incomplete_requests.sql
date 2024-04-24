select
	u.first_name, u.username,
	ar.*,
	dm.*
from application_requests as ar
	left join users as u
		on ar.user_id = u.user_id
	left join description_messages as dm
		on ar.id = dm.application_request_id
where 1=1
	and ar.ready = 0
	and ar.other_members_text is not null
order by ar.id desc, dm.id;

select
	ar.user_id,
	u.first_name,
	u.last_name,
	u.username,
	ar.id as request_id,
	ar.created_on,
	group_concat(dm.type, ', ') as description_messages_type_concat,
	count(dm.id) as description_messages_count
from application_requests as ar
	left join users as u
		on ar.user_id = u.user_id
	left join description_messages as dm
		on ar.id = dm.application_request_id
	left join ( -- user_id with a request that was evaluated
		select user_id
		from application_requests
		where status is not null
	) as er -- evaluated requests
		on ar.user_id = er.user_id
where 1=1
	and ar.ready = 0
	and ar.other_members_text is not null
	and er.user_id is null  -- ignore users with evaluated requests
group by
	ar.user_id,
	u.first_name,
	u.last_name,
	u.username,
	ar.id,
	ar.created_on
order by ar.id desc;
