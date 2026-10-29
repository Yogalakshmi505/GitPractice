from odoo import api, fields, models

SPEC_PARAMETERS = [
    ('caster', 'Caster'), ('camber', 'Camber'), ('sai', 'SAI'),
    ('ind_toe', 'Individual Toe'), ('total_toe', 'Total Toe'), ('thrust', 'Thrust Angle'),
]
WHEEL_PARAMETERS = [('camber', 'Camber'), ('caster', 'Caster'), ('toe', 'Toe')]
POSITIONS = [('FL', 'Front Left'), ('FR', 'Front Right'), ('RL', 'Rear Left'), ('RR', 'Rear Right')]
SPEC_FOR_WHEEL = {'caster': 'caster', 'camber': 'camber', 'toe': 'ind_toe'}
READINGS_BY_AXLE = {'front': ['camber', 'caster', 'toe'], 'rear': ['camber', 'toe']}
READING_ORDER = [p for p, _label in WHEEL_PARAMETERS]


def _axle_of(position):
    return 'front' if position and position[0] == 'F' else 'rear'


class AlignmentSpec(models.Model):
    _name = 'tyre.alignment.spec'
    _description = 'Alignment Specification'
    _order = 'name'

    name = fields.Char('Vehicle model', required=True)
    wheel_size = fields.Char()
    line_ids = fields.One2many('tyre.alignment.spec.line', 'spec_id', string='Values')


class AlignmentSpecLine(models.Model):
    _name = 'tyre.alignment.spec.line'
    _description = 'Alignment Specification Value'
    _order = 'spec_id, axle, sequence, id'

    spec_id = fields.Many2one('tyre.alignment.spec', required=True, ondelete='cascade')
    axle = fields.Selection([('front', 'Front'), ('rear', 'Rear')], required=True, default='front')
    parameter = fields.Selection(SPEC_PARAMETERS, required=True)
    sequence = fields.Integer(default=10)
    min_val = fields.Float('Min', digits=(5, 2))
    pref_val = fields.Float('Pref', digits=(5, 2))
    max_val = fields.Float('Max', digits=(5, 2))
    cross_val = fields.Float('Cross', digits=(5, 2))
    has_range = fields.Boolean('Has min/max', default=True)

    def _check(self, value):
        """'ok' inside min-max, 'out' outside, 'none' when there is no range."""
        if not self or not self.has_range:
            return 'none'
        return 'ok' if self.min_val <= value <= self.max_val else 'out'


class AlignmentJob(models.Model):
    _name = 'tyre.alignment.job'
    _description = 'Alignment Job'
    _order = 'id desc'

    name = fields.Char(default='New', readonly=True, copy=False)
    vehicle_id = fields.Many2one('fleet.vehicle', required=True)
    spec_id = fields.Many2one('tyre.alignment.spec', string='Specification')
    date = fields.Datetime(default=fields.Datetime.now)
    state = fields.Selection(
        [('measuring', 'Measuring'), ('done', 'Done'), ('cancel', 'Cancelled')],
        default='measuring', string='Status')
    reading_ids = fields.One2many('tyre.alignment.reading', 'job_id', string='Readings')

    @api.model_create_multi
    def create(self, vals_list):
        jobs = super().create(vals_list)
        for job in jobs:
            job.name = 'ALN/%05d' % job.id
            job._ensure_readings()
        return jobs

    def _ensure_readings(self):
        Reading = self.env['tyre.alignment.reading']
        for job in self:
            existing = {(r.position, r.parameter) for r in job.reading_ids}
            vals = [{'job_id': job.id, 'position': pos, 'parameter': param}
                    for pos, _label in POSITIONS
                    for param in READINGS_BY_AXLE[_axle_of(pos)]
                    if (pos, param) not in existing]
            if vals:
                Reading.create(vals)

    def _spec_line(self, axle, spec_param):
        return self.spec_id.line_ids.filtered(
            lambda l: l.axle == axle and l.parameter == spec_param)[:1]

    def _reading_info(self, reading):
        line = self._spec_line(_axle_of(reading.position), SPEC_FOR_WHEEL[reading.parameter])
        return {
            'param': reading.parameter,
            'label': dict(WHEEL_PARAMETERS)[reading.parameter],
            'value': reading.value,
            'status': line._check(reading.value),
        }

    def _position_info(self, position):
        readings = self.reading_ids.filtered(lambda r: r.position == position).sorted(
            lambda r: READING_ORDER.index(r.parameter))
        tyre = self.env['tyre.master'].search([
            ('vehicle_id', '=', self.vehicle_id.id), ('position', '=', position),
            ('state', '=', 'active')], limit=1)
        return {
            'pos': position,
            'label': dict(POSITIONS)[position],
            'tyre': tyre._tyre_info() if tyre else False,
            'readings': [self._reading_info(r) for r in readings],
        }

    # ---------- called from the JS alignment screens ----------
    @api.model
    def start_alignment(self, vehicle_id, spec_id, mode):
        open_jobs = self.search([('vehicle_id', '=', vehicle_id), ('state', '=', 'measuring')])
        if mode == 'continue' and open_jobs:
            job = open_jobs[0]
            if spec_id:
                job.spec_id = spec_id
            return job.id
        open_jobs.write({'state': 'cancel'})
        return self.create({'vehicle_id': vehicle_id, 'spec_id': spec_id or False}).id

    def get_spec_table(self):
        self.ensure_one()
        spec = self.spec_id
        labels = dict(SPEC_PARAMETERS)

        def rows(axle):
            return [{
                'label': labels[line.parameter],
                'per_side': line.parameter not in ('total_toe', 'thrust'),
                'has_range': line.has_range,
                'min': line.min_val, 'pref': line.pref_val,
                'max': line.max_val, 'cross': line.cross_val,
            } for line in spec.line_ids if line.axle == axle]

        return {'name': spec.name or '', 'wheel_size': spec.wheel_size or '',
                'front': rows('front'), 'rear': rows('rear')}

    def get_wheel_view(self):
        self.ensure_one()
        positions = [self._position_info(p) for p, _label in POSITIONS]
        statuses = [r['status'] for p in positions for r in p['readings']]
        if 'out' in statuses:
            summary = 'out'
        elif 'ok' in statuses:
            summary = 'ok'
        else:
            summary = 'nospec'
        return {'job': self.name, 'vehicle': self.vehicle_id.display_name,
                'positions': positions, 'summary': summary}

    def get_axle_info(self, axle):
        self.ensure_one()
        return {
            'axle': axle,
            'label': 'Front axle' if axle == 'front' else 'Rear axle',
            'wheels': [self._position_info(p) for p, _label in POSITIONS if _axle_of(p) == axle],
        }

    def action_done(self):
        self.write({'state': 'done'})

    def action_open_alignment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'tyre_tracking_alignment',
            'name': self.name,
            'context': {'alignment_job_id': self.id},
        }


class AlignmentReading(models.Model):
    _name = 'tyre.alignment.reading'
    _description = 'Alignment Reading'
    _order = 'job_id, position, parameter'

    job_id = fields.Many2one('tyre.alignment.job', required=True, ondelete='cascade')
    position = fields.Selection(POSITIONS, required=True)
    parameter = fields.Selection(WHEEL_PARAMETERS, required=True)
    value = fields.Float('Value (°)', digits=(5, 2))
    status = fields.Selection(
        [('ok', 'Within spec'), ('out', 'Out of spec'), ('none', 'No spec')],
        compute='_compute_status')

    @api.depends('value', 'position', 'parameter', 'job_id.spec_id')
    def _compute_status(self):
        for reading in self:
            line = reading.job_id._spec_line(
                _axle_of(reading.position), SPEC_FOR_WHEEL.get(reading.parameter, ''))
            reading.status = line._check(reading.value)
