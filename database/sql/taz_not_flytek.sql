select
	cmt.user_id,
	u.first_name,
	u.last_name,
	u.username,
	cmt.status as status_taz,
	cmu.user_id as presenza_flytek,
	cmu.status as status_flytek
from chat_members as cmt
	left join users as u
		on u.user_id = cmt.user_id
	left join chat_members as cmu
		on cmu.user_id = cmt.user_id
		and cmu.chat_id = -1001599255228 -- users
where 1=1
	and cmt.chat_id = -1001873911776 -- taz
	and (cmu.user_id is null or cmu.status not in ('creator', 'administrator', 'member', 'restricted'))
order by
	cmt.user_id;
