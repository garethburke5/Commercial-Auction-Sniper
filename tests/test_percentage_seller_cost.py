from acquisition_financials import percentage_seller_cost

def model(*clauses,kind='special_conditions'):
 return {'documents':[{'document':'Terms','type':kind}], 'source_pages':[{'document':'Terms','document_sha256':'test','page':i+1,'text':c} for i,c in enumerate(clauses)]}
def clause(rate):
 return f'The Buyer shall pay to the Seller an amount equal to {rate}% plus an amount equivalent to the current rate of value added tax of the Price as a contribution towards the legal and agent’s costs incurred by the Seller.'
def test_percentage_scales_with_price_and_preserves_vat():
 r=percentage_seller_cost(model(clause(3.2)),250000)['cost']
 assert (r['base'],r['vat'],r['amount'])==(8000,1600,9600)
 assert percentage_seller_cost(model(clause(3.2)),300000)['cost']['amount']==11520
 assert r['evidence'][0]['page']==1
def test_does_not_turn_deposit_or_other_document_into_seller_cost():
 assert percentage_seller_cost(model('The buyer pays a 10% deposit.'),250000)['cost'] is None
 assert percentage_seller_cost(model(clause(3.2),kind='lease'),250000)['cost'] is None
def test_conflicting_percentages_are_not_silently_selected():
 r=percentage_seller_cost(model(clause(3.2),clause(2)),250000)
 assert r['conflict'] and r['cost'] is None
 assert not percentage_seller_cost(model(clause(3.2),clause(3.2)),250000)['conflict']
