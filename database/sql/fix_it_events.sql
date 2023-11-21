update events
set region = 'Italia'
where region in (
	'Nord Italia',
	'Centro Italia',
	'Sud Italia',
	'Sardegna',
	'Sicilia'
);
