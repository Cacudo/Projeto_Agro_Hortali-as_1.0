from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# Banco de dados temporário em memória (Lista de dicionários)
registros = [
    {
        'id': 1,
        'talhao': 'Talhão Norte 01',
        'cultura': 'Soja',
        'area_ha': 50.0,
        'dosagem_l_ha': 2.5,
        'volume_total': 125.0
    }
]
proximo_id = 2

@app.route('/')
def index():
    return render_template('index.html', registros=registros)

@app.route('/cadastrar', methods=['POST'])
def cadastrar():
    global proximo_id
    talhao = request.form.get('talhao')
    cultura = request.form.get('cultura')
    area_ha = float(request.form.get('area_ha'))
    dosagem_l_ha = float(request.form.get('dosagem_l_ha'))
    
    # Regra de negócio / Cálculo matemático do Agro
    volume_total = area_ha * dosagem_l_ha

    novo_registro = {
        'id': proximo_id,
        'talhao': talhao,
        'cultura': cultura,
        'area_ha': area_ha,
        'dosagem_l_ha': dosagem_l_ha,
        'volume_total': round(volume_total, 2)
    }
    
    registros.append(novo_registro)
    proximo_id += 1
    return redirect(url_for('index'))

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    registro = next((r for r in registros if r['id'] == id), None)
    if not registro:
        return redirect(url_for('index'))

    if request.method == 'POST':
        registro['talhao'] = request.form.get('talhao')
        registro['cultura'] = request.form.get('cultura')
        registro['area_ha'] = float(request.form.get('area_ha'))
        registro['dosagem_l_ha'] = float(request.form.get('dosagem_l_ha'))
        
        # Recálculo
        registro['volume_total'] = round(registro['area_ha'] * registro['dosagem_l_ha'], 2)
        return redirect(url_for('index'))

    return render_template('editar.html', registro=registro)

@app.route('/deletar/<int:id>')
def deletar(id):
    global registros
    registros = [r for r in registros if r['id'] != id]
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)