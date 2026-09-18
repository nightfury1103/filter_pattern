from __future__ import annotations

import copy

import pytest

from filter_pattern.rrg_comparison import matched_rows, normalize_points, make_signals, paired_comparison


def point(day, x=101., y=101.):
    return {"date":day,"x":x,"y":y,"price":100.}


def history_row(day, index=100):
    return {"date":day,"index":index,"outcomes":{"10":{"return_pct":2.,"exit_date":"2024-02-01"}},
            "forecasts":{"price_only":{"p_up":.8,"bias":"LONG"},"context":{"p_up":.4,"bias":"WAIT"},
                         "ema":{"bias":"LONG"},"always_long":{"bias":"LONG"}}}


def test_normalization_removes_current_bar_sorts_and_rejects_invalid():
    rows=[point("20240103"),point("20240101"),point("20240102")]
    assert [p['date'] for p in normalize_points(rows,"2024-01-03")]==["2024-01-01","2024-01-02"]
    with pytest.raises(ValueError,match="Duplicate"):
        normalize_points([point("20240101"),point("2024-01-01")],"2024-02-01")
    with pytest.raises(ValueError,match="Invalid"):
        normalize_points([point("20240101",x=float('nan'))],"2024-02-01")
    with pytest.raises(ValueError,match="Non-daily"):
        normalize_points([{**point("20240101"),"end":"2024-01-02 23:59:00"}],"2024-02-01")


def test_center_spy_is_neutral_and_original_rejection_is_not_short():
    points=[point(f"2024-01-0{i}",100.,100.) for i in range(1,6)]
    for r in make_signals(points).values():
        assert [r[k] for k in ('rrg_x','rrg_y','rrg_intent')]==['WAIT']*3
    falling=[point(f"2024-01-0{i}",99.,101-i) for i in range(1,6)]
    last=make_signals(falling)['2024-01-05']
    assert last['rrg_y']=='SHORT'
    assert last['rrg_intent']=='WAIT'


def test_production_intent_is_causal_and_requires_four_points():
    points=[point(f"2024-01-0{i}",99.,99+i) for i in range(1,7)]
    full=make_signals(points)
    assert full['2024-01-03']['rrg_intent']=='WAIT'
    assert full['2024-01-04']['rrg_intent']=='LONG'
    assert make_signals(points[:4])['2024-01-04']==full['2024-01-04']
    changed=copy.deepcopy(points)
    changed[-1]['y']=-1000
    assert make_signals(changed)['2024-01-04']==full['2024-01-04']


def test_matched_dates_no_weekend_forward_fill_no_mutation_and_price_scale():
    history=[history_row('2024-01-05'),history_row('2024-01-06',101),history_row('2024-01-08',103)]
    original=copy.deepcopy(history)
    points=[point('2024-01-05'),point('2024-01-08')]
    rows,audit=matched_rows(history,points,{'2024-01-05':100000.,'2024-01-08':98000.},1000.)
    assert history==original
    assert [r['date'] for r in rows]==['2024-01-05','2024-01-08']
    assert audit['missing_rrg_dates']==['2024-01-06']
    assert audit['price_mismatches_over_1pct'][0]['date']=='2024-01-08'
    assert rows[0]['forecasts']['price_direction']['bias']=='LONG'
    assert rows[0]['forecasts']['context_direction']['bias']=='SHORT'


def test_pairs_only_count_shared_signals_flat_incorrect_for_both():
    rows=[history_row(f'2024-01-0{i}') for i in range(1,5)]
    for r in rows:
        r['forecasts']['a']={'bias':'LONG'}
        r['forecasts']['b']={'bias':'SHORT'}
    rows[0]['forecasts']['b']['bias']='WAIT'
    rows[1]['outcomes']['10']['return_pct']=-2
    rows[2]['outcomes']['10']['return_pct']=0
    result=paired_comparison(rows,'a','b')
    assert result['shared_signals']==3
    assert result['wins_a']==result['wins_b']==1
    assert result['difference_a_minus_b']==0
    assert result['block_ci95_difference'] is None
