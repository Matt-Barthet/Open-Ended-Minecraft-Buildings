import matplotlib.pyplot as plt
from matplotlib.colors import LightSource

from Evaluation.DataLoading import load_populations, load_autoencoder, load_seed_set, load_training_set
from Evaluation.EvalutationConfig import *
from Evaluation.Test import new_voxel_plot


def AVG_Plot(label, pool, args):
    results = np.load("Results/Qualitative/AVG_Properties.npy", allow_pickle=True).item()[label]
    means = []
    cis = []
    for phase in range(phases_to_evaluate):
        means.append(results[phase][args[0]]["Mean"])
        cis.append(results[phase][args[0]]["CI"])
    return range(phases_to_evaluate), np.asarray(means), np.asarray(cis)


def AVG_Properties(experiments, args=None):
    results_dict = {}
    for experiment in experiments:
        experiment_results = []
        populations = load_populations(experiment)
        for phase in range(phases_to_evaluate):
            phase_results = {}
            pops = populations[phase]
            for population in range(len(pops)):
                properties = expressive(pops[population])
                for key in properties.keys():
                    try:
                        phase_results[key] += properties[key]
                    except KeyError:
                        phase_results.update({key: properties[key]})
            for key in phase_results.keys():
                phase_results[key] = {"Mean": np.round(np.mean(phase_results[key]), 2),
                                      "CI": np.round(confidence_interval(phase_results[key], 1.96), 2)}
            experiment_results.append(phase_results)
            print({experiment: experiment_results})
        results_dict.update({experiment: experiment_results})
    np.save("Results/Qualitative/AVG_Properties.npy", results_dict)
    return results_dict


def symmetry(lattice, h_bound, v_bound, d_bound):
    symmetry = 0
    symmetry += height_symmetry(lattice, h_bound, v_bound, d_bound)
    symmetry += width_symmetry(lattice, h_bound, v_bound, d_bound)
    symmetry += depth_symmetry(lattice, h_bound, v_bound, d_bound)
    return symmetry / 12000


def surface_ratio(lattice, h_bound, v_bound, d_bound):
    height = v_bound[1]
    depth = (d_bound[1] - d_bound[0])
    width = (h_bound[1] - h_bound[0])
    bb_area = 2 * (depth * width + depth * height + width * height)
    bb_volume = width * depth * height

    roof_count = 0
    walls = 0
    floor_count = 0
    interior_count = 0
    total_count = 0
    for (x, y, z) in value_range:
        if lattice[x][y][z] == 0:
            continue
        total_count += 1
        if lattice[x][y][z] == 1:
            interior_count += 1
        elif lattice[x][y][z] == 2:
            walls += 1
        elif lattice[x][y][z] == 3:
            floor_count += 1
        elif lattice[x][y][z] == 4:
            roof_count += 1

    try:
        surface_area = (walls + roof_count + floor_count) / total_count
        floor_count /= total_count
        walls /= total_count
        roof_count /= total_count
        volume_vs_bb = total_count / bb_volume
        bb_vs_total = bb_volume / lattice_dimensions[0] ** 3
        return {"Surface Area": [surface_area], "Floor": [floor_count], "Walls": [walls], "Roof": [roof_count],
                "Building vs BB Volume Ratio": [volume_vs_bb], "BB vs Total Volume Ratio": [bb_vs_total]}
    except ZeroDivisionError:
        print("Empty Lattice Found")
        return 0


def draw_lines_fig(fig):
    line = plt.Line2D((0.12, 0.12), (.1, .9), color="k", linewidth=2)
    fig.add_artist(line)
    line = plt.Line2D((0.91, 0.91), (.1, .9), color="k", linewidth=2)
    fig.add_artist(line)
    line = plt.Line2D((.275, .275), (.1, .9), color="k", linewidth=2)
    fig.add_artist(line)
    line = plt.Line2D((.4325, .4325), (.1, .9), color="k", linewidth=2)
    fig.add_artist(line)
    line = plt.Line2D((.595, .595), (.1, .9), color="k", linewidth=2)
    fig.add_artist(line)
    line = plt.Line2D((.7575, .7575), (.1, .9), color="k", linewidth=2)
    fig.add_artist(line)
    return fig


def novelty_search2(genome, compressed_population):
    distances = []
    for neighbour in list(compressed_population.values()):
        distance = 0
        for element in range(len(neighbour)):
            distance += np.square(genome[element] - neighbour[element])
        distances.append(np.sqrt(distance))
    distances = np.sort(distances)
    return np.round(np.mean(distances[1:6]), 2)


def expressive(phase):
    ratios = {}
    stabilities = []
    x_symmetry = []
    y_symmetry = []
    z_symmetry = []
    converted = [convert_to_integer(lattice) for lattice in phase]
    for lattice in converted:
        horizontal_bounds, depth_bounds, vertical_bounds = bounding_box(lattice)
        x_symmetry.append(width_symmetry(lattice, horizontal_bounds, depth_bounds, vertical_bounds))
        y_symmetry.append(height_symmetry(lattice, horizontal_bounds, depth_bounds, vertical_bounds))
        z_symmetry.append(depth_symmetry(lattice, horizontal_bounds, depth_bounds, vertical_bounds))
        new_ratios = surface_ratio(lattice, horizontal_bounds, vertical_bounds, depth_bounds)
        for ratio in new_ratios.keys():
            try:
                ratios[ratio] += new_ratios[ratio]
            except KeyError:
                ratios.update({ratio: new_ratios[ratio]})
        stabilities.append(stability(lattice)[1])
    result = {"Instability": stabilities, "X-Symmetry": x_symmetry, "Y-Symmetry": y_symmetry, "Z-Symmetry": z_symmetry}
    for key in ratios.keys():
        result.update({key: ratios[key]})
    return result


def expressive_analysis(experiments, xlabel, ylabel, dict=None):
    fig, axes = plt.subplots(nrows=3, ncols=3, figsize=(8, 8), sharex=True, sharey=True)
    plt.setp(axes[-1, :], xlabel=xlabel)
    plt.setp(axes[:, 0], ylabel=ylabel)

    try:
        metric1 = dict['Seed'][xlabel]
        metric2 = dict['Seed'][ylabel]
        print("Seed data found!")
    except:
        print("No seed data found, calculating new points")
        seed = load_seed_set()
        metric1, metric2 = expressive(seed, xlabel, ylabel)
        dict["Seed"].update({xlabel: metric1, ylabel: metric2})

    expressive_graph(fig, axes[0, 0], x=metric1, y=metric2, title="Seed", x_label=xlabel, y_label=ylabel)
    counter = 1
    locs = [[0, 0], [0, 1], [0, 2], [1, 0], [1, 1], [1, 2], [2, 0], [2, 1], [2, 2]]
    for experiment in experiments:
        try:
            metric1 = dict[experiment][xlabel]
            metric2 = dict[experiment][ylabel]
            print("{} data found!".format(experiment))
        except:
            print("{} data not found! Calculating new points..".format(experiment))
            phase = load_training_set(experiment)[-1]
            metric1, metric2 = expressive(phase, xlabel, ylabel)
            dict[experiment].update({xlabel: metric1, ylabel: metric2})
        expressive_graph(fig, axes[locs[counter][0]][locs[counter][1]], x=metric1, y=metric2, title=experiment,
                         x_label=xlabel, y_label=ylabel)
        counter += 1

    fig.subplots_adjust(bottom=0.15)
    fig.tight_layout()
    fig.savefig("../Expressive-{}vs{}.png".format(xlabel, ylabel))
    fig.show()


def compress_lattice(pool, encoder, lattice, counter, original, compressed):
    original.update({counter: convert_to_integer(lattice)})
    compressed.update({counter: encoder.predict(lattice[None], verbose=0)[0]})
    counter += 1
    return counter


def compute_fitness(pool, compressed):
    jobs = []
    for key in compressed.keys():
        parameters = (compressed[key], compressed)
        jobs.append(pool.apply_async(novelty_search2, parameters))

    fitness = {}
    for job, genome_id in zip(jobs, compressed.keys()):
        fitness.update({genome_id: job.get()})
    return fitness


def sort_lattices(fitness, original):
    sorted_keys = [k for k, _ in sorted(fitness.items(), key=lambda item: item[1])]
    sorted_lattices = [original[key] for key in sorted_keys]
    return sorted_lattices


def process_population(pool, encoder, population_data):
    fitness = {}
    original = {}
    compressed = {}
    counter = 0

    for lattice in population_data:
        counter = compress_lattice(pool, encoder, lattice, counter, original, compressed)

    fitness = compute_fitness(pool, compressed)
    sorted_lattices = sort_lattices(fitness, original)

    return sorted_lattices


def process_phase(pool, experiment, phase):
    print("Starting Phase {}".format(phase))
    encoder, _ = load_autoencoder(experiment, phase)
    phases = load_populations(experiment)
    phase_data = {}

    for population_id in range(0, 10):
        print("Processing Population {}".format(population_id))
        population_data = phases[phase][population_id]
        sorted_lattices = process_population(pool, encoder, population_data)
        phase_data[population_id] = sorted_lattices

    return phase_data
def compress_populations(labels, pool):
    all_experiment_data = {}

    for experiment in labels:
        print("Starting Experiment {}".format(experiment))
        experiment_data = {}

        for phase in range(10):
            phase_data = process_phase(pool, experiment, phase)
            experiment_data[phase] = phase_data

        all_experiment_data[experiment] = experiment_data

    np.save("./Results/Qualitative/all_experiment_data.npy", all_experiment_data)


import numpy as np

def save_data_as_npy(labels, populations):
    all_experiment_data = np.load("./Results/Qualitative/all_experiment_data.npy", allow_pickle=True).item()

    experiment_count = len(labels)

    for population_id in populations:
        for phase in range(10):
            print("Starting Population {} Phase {}".format(population_id, phase))

            for idx, experiment in enumerate(labels):
                print("Starting Experiment {}".format(experiment))

                experiment_data = all_experiment_data.get(experiment, None)
                if experiment_data is None:
                    print(f"No data found for experiment {experiment}")
                    continue

                phase_data = experiment_data.get(phase, None)
                if phase_data is None:
                    print(f"No data found for phase {phase} in experiment {experiment}")
                    continue

                sorted_lattices = phase_data[population_id]

                for number, plot in enumerate(np.linspace(len(sorted_lattices) - 1, 0, 3, dtype=int)):
                    building_name = f"Building_{phase}_{experiment}_{number}.npy"
                    building_data = sorted_lattices[plot]
                    np.save(building_name, building_data)

                    print(f"Saved building data as {building_name}")


def load_and_plot_data(labels, populations):
    xlabels = ['Most\nNovel', 'Mid\nNovel', 'Least\nNovel']
    all_experiment_data = np.load("./Results/Qualitative/all_experiment_data.npy", allow_pickle=True).item()

    experiment_count = len(labels)

    for population_id in populations:  # Swap this loop with the one below
        for phase in range(10):  # Swap this loop with the one above
            print("Starting Population {} Phase {}".format(population_id, phase))

            fig = draw_lines_fig(plt.figure(figsize=(12, 7)))
            # fig.suptitle("Range of Generated Content - Population {} Phase {}".format(population_id+1, phase+1), fontsize=18)

            for idx, experiment in enumerate(labels):
                print("Starting Experiment {}".format(experiment))

                experiment_data = all_experiment_data.get(experiment, None)
                if experiment_data is None:
                    print(f"No data found for experiment {experiment}")
                    continue

                phase_data = experiment_data.get(phase, None)
                if phase_data is None:
                    print(f"No data found for phase {phase} in experiment {experiment}")
                    continue

                sorted_lattices = phase_data[population_id]

                for number, plot in enumerate(np.linspace(len(sorted_lattices) - 1, 0, 3, dtype=int)):

                    # changing subplot location based on experiment index
                    ax = fig.add_subplot(3, experiment_count, idx + 1 + experiment_count * number, projection='3d')

                    ax.set_axis_off()
                    if number == 0:  # Add experiment name at the top of first subplot of each experiment
                        ax.set_title('{}'.format(experiment), fontsize=15)
                    if idx == 0:
                        ax.text(-34 * 16, 0, -5 * 16, s=xlabels[number], fontsize=15)

                    new_voxel_plot(fig, ax, sorted_lattices[plot])

            plt.savefig("./Figures/Qualitative/population-{}-phase-{}.png".format(population_id, phase))
            plt.close(fig)


if __name__ == "__main__":
    #pool = Pool(16)
    #compress_populations(labels, pool)
    #load_and_plot_data(labels, [0])
    save_data_as_npy(labels, [0])
    #pool.close()
    #pool.join()