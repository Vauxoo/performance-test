import odoorpc
import click
import random
import string


@click.command()
@click.option('-po', default='admin',
              help='Password Origin')
@click.option('-dbo', default='performance',
              help='DB Origin')
@click.option('-uo', default='admin',
              help='your email or login')
@click.option('-l', '--line_count', default=1,
              help='IF of the sale order that you want to duplicate')
def duplicate_sale_order(po, dbo, uo, line_count):
    """
    If you dont know how to execute this script use
    python generate_sale.py --help

    Example:
        python generate_sale.py -po passwordorigin -uo userorigin -dbo
        dborigin -si sale_id2
    you still need to modify the IP, Protocol, and Portparameters.
    """
    con = odoorpc.ODOO(
        'localhost',
        timeout=9999,
        port=8069)
    con.login(dbo, uo, po, )
    pids = con.execute('product.product',
                       'search',
                       [('type', '<>', 'service'), ('type', '<>', 'consu')])
    sale_order_id = con.execute('sale.order', 'create', {
        'partner_id': 20,
        })
    click.echo('+ Created order : {}'.format(sale_order_id))
    stock = con.execute('stock.location', 'search', [('name', '=', 'Stock')])
    destination = con.execute('stock.location', 'create',
                              {'name': 'destination_location', 'usage': 'inventory'})
    for linec in range(0, line_count):
        pid = random.choice(pids)
        con.execute(
            'sale.order.line',
            'create',
            {
                'order_id': sale_order_id,
                'product_id': pid,
                'product_uom_qty': 5,
                'name': 'Random product line {}'.format(linec),
            }
        )
        name = u''.join(random.choice(string.letters+string.digits) for letter in range(6))
        lot_id = con.execute('stock.production.lot',
                             'create',
                             {'name': name, 'product_id': pid})
        wiz_id = con.execute('stock.change.product.qty', 'create',
                             {'location_id': 12, 'new_quantity': 100,
                              'product_id': pid, 'lot_id': lot_id})
        con.execute('stock.change.product.qty', 'change_product_qty', wiz_id)
    click.echo('+- Added {} lines to order {}'.format(line_count, sale_order_id))
    sale_order = con.env['sale.order']
    order = sale_order.browse(sale_order_id)
    order.action_button_confirm()
    res_order = order.manual_invoice()
    click.echo('+- Validated sale order')
    invoice = con.env['account.invoice']
    sale_invoice = invoice.browse(res_order['res_id'])
    sale_invoice.signal_workflow('invoice_open')
    sale_invoice.invoice_print()
    click.echo('+- Validated invoice : {}'.format(res_order['res_id']))
    validated = 0
    while validated != 2:
        click.echo('+- Validating pickings')
        for pick in order.picking_ids:
            click.echo('+-- {id} state: {state}'.format(id=pick.id, state=pick.state))
            pick.write({'move_type': 'one'})
            pick.write({'check_invoice': 'no_check'})
            if pick.state in ('confirmed', 'assigned', 'waiting'):
                item_details_list = []
                click.echo('+-- Validating picking {}'.format(pick.id))
                for ln in pick.move_lines:
                    pid = ln.product_id.id
                    uom = con.env['stock.move'].search([('product_id', '=', pid)])
                    puom = con.env['stock.move'].browse(uom[0])
                    item = con.execute('stock.transfer_details_items',
                                       'create',
                                       {'product_id': pid,
                                        'sourceloc_id': stock[0], 'destinationloc_id': destination,
                                        'product_uom_id': puom.product_uom.id, 'quantity': 5})
                    item_details_list.append(item)
                    pick.force_assign()
                created_id = con.execute('stock.transfer_details',
                                         'create',
                                         {'picking_id': pick.id,
                                          'picking_source_location_id': stock[0],
                                          'picking_destination_location_id': destination,
                                          'item_ids': [(6, 0, item_details_list)]})
                try:
                    con.execute('stock.transfer_details',
                                'do_detailed_transfer', [created_id])
                except odoorpc.error.RPCError as error:
                    click.echo(error.info.get('data').get('debug'))
                    continue
            else:
                validated += 1
                click.echo('+-- Validated {}'.format(validated))
    click.echo('+ Process Completed')
    amount = sale_invoice.amount_total
    period_ids = con.env['account.period'].search([])
    period_id = con.env['account.period'].browse(period_ids[0])
    period = period_id.id
    partner = sale_invoice.partner_id
    journal = sale_invoice.journal_id.id
    name = sale_invoice.name
    account = sale_invoice.account_id
    voucher_data = {
        'partner_id': partner.id,
        'amount': amount,
        'journal_id': journal,
        'period_id': period,
        'account_id': account.id,
        'reference': sale_invoice.name,
        'currency_id': sale_invoice.currency_id.id
    }
    voucher_id = con.execute('account.voucher', 'create', voucher_data)
    con.env['account.voucher'].browse(voucher_id)
    for ln in sale_invoice.move_id:
        con.execute('account.voucher.line', 'create',
                    {'name': name, 'amount': amount,
                     'voucher_id': voucher_id,
                     'partner_id': partner.id,
                     'account_id': account.id,
                     'currency_id': sale_invoice.currency_id.id,
                     'move_line_id': ln.line_id.id})
    con.execute('account.voucher', 'button_proforma_voucher', [voucher_id])

if __name__ == '__main__':
    duplicate_sale_order()
