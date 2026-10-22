from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# Lista em memória guardando os registos
registos = []

def calcular_metricas():
    total_talhoes = len(registos)
    total_area = sum(float(r['area']) for r in registos) if registos else 0
    total_volume = sum(float(r['volume_total']) for r in registos) if registos else 0
    return total_talhoes, round(total_area, 2), round(total_volume, 2)

@app.route('/')
@app.route('/visao-geral')
def visao_geral():
    total_talhoes, total_area, total_volume = calcular_metricas()
    return render_template(
        'index.html',
        registos=registos,
        total_talhoes=total_talhoes,
        total_area=total_area,
        total_volume=total_volume,
        secao_ativa='visao_geral'
    )

@app.route('/pulverizacao')
def pulverizacao():
    total_talhoes, total_area, total_volume = calcular_metricas()
    return render_template(
        'index.html',
        registos=registos,
        total_talhoes=total_talhoes,
        total_area=total_area,
        total_volume=total_volume,
        secao_ativa='pulverizacao'
    )

@app.route('/relatorios')
def relatorios():
    total_talhoes, total_area, total_volume = calcular_metricas()
    return render_template(
        'index.html',
        registos=registos,
        total_talhoes=total_talhoes,
        total_area=total_area,
        total_volume=total_volume,
        secao_ativa='relatorios'
    )

@app.route('/configuracoes')
def configuracoes():
    total_talhoes, total_area, total_volume = calcular_metricas()
    return render_template(
        'index.html',
        registos=registos,
        total_talhoes=total_talhoes,
        total_area=total_area,
        total_volume=total_volume,
        secao_ativa='configuracoes'
    )

@app.route('/add', methods=['POST'])
def add():
    talhao = request.form.get('talhao')
    cultura = request.form.get('cultura')
    area = float(request.form.get('area', 0))
    dosagem = float(request.form.get('dosagem', 0))
    volume_total = area * dosagem

    novo_id = (registos[-1]['id'] + 1) if registos else 1

    registos.append({
        'id': novo_id,
        'talhao': talhao,
        'cultura': cultura,
        'area': area,
        'dosagem': dosagem,
        'volume_total': round(volume_total, 2)
    })

    return redirect(url_for('visao_geral'))

@app.route('/deletar/<int:id>')
def deletar(id):
    global registos
    registos = [r for r in registos if r['id'] != id]
    return redirect(url_for('visao_geral'))

if __name__ == '__main__':
    app.run(debug=True)