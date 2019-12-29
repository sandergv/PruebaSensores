from datetime import datetime
import csv

csv_file = "on_change_data.csv"

csv_data = None
temp_data = []
humi_data = []

with open(csv_file, 'r') as f:
    csv_data = csv.reader(f)

    for row in csv_data:
        if row[2] == "Temperature":
            temp_data.append(row)
        elif row[2] == "Humidity":
            humi_data.append(row)
f.close()


def get_info(data):
    dt = datetime.strptime(data[0][0], '%Y-%m-%d %H:%M:%S')    
    hour = dt.hour
    acum = 0
    tipo = data[0][2]
    key = f"{dt.month}-{dt.day}-{dt.hour}"
    info_dict = {key: {"type": tipo, "list": [], "media": 0}}

    # Cantidad de cambios por hora y el promedio del valor
    for row in data:
        dt = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')

        if dt.hour != hour:
            if info_dict[key]['list']:
                media = acum//len(info_dict[key]['list'])
                info_dict[key]['media'] = media
            key = f"{dt.month}-{dt.day}-{dt.hour}"
            info_dict.update({key: {"type": tipo, "list": [], "media": 0}})
            info_dict[key]['list'].append(row)
            acum = int(row[3])
            hour = dt.hour
        else:
            info_dict[key]['list'].append(row)
            acum += int(row[3])
        

    media = acum//len(info_dict[key]['list'])
    info_dict[key]['media'] = media

    return info_dict

def show_info(info_dict):
    for k, v in info_dict.items():
        print(f"Tipo: {v['type']}, hora: {k}, len: " + str(len(v['list'])) +
            f", media: {v['media']}")


temp_info = get_info(temp_data)
humi_info = get_info(humi_data)

show_info(temp_info)
show_info(humi_info)