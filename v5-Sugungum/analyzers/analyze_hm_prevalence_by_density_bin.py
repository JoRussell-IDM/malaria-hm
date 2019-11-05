import os, re
import sqlite3
import pandas as pd
import numpy as np
import seaborn as sns
#Plotting
import matplotlib.pyplot as plt
from scipy.special import gammaln

from simtools.Analysis.BaseAnalyzers import BaseAnalyzer
from simtools.Analysis.AnalyzeManager import AnalyzeManager
from calibtool.analyzers.Helpers import season_channel_age_density_csv_to_pandas
from add_inputEIR_framework.reference_data.Garki_population_summary import *
from calibtool.LL_calculators import dirichlet_multinomial_pandas

def get_reference_data(self):
    dir_path = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..', 'reference_data'))
    dfFileName = os.path.join(dir_path, 'Garki_df.csv')


    df = pd.read_csv(dfFileName)

    ref_df = df[df['Village'] == self.metadata['village']]

    age_bins = self.metadata['age_bins']
    age_bin_labels = self.metadata['age_bin_labels']
    density_bins = self.metadata['density_bins']
    density_bin_edges = self.metadata['density_bin_edges']
    uL_per_field = 0.5 / 200.0  # from Garki PDF - page 111 - 0.5 uL per 200 views
    pfprBins = 1 - np.exp(-np.asarray(density_bins) * uL_per_field)

    all_surveys_ref_df = pd.DataFrame(columns=['month', 'age_bin', 'density_bin', 'count'])

    df = ref_df
    df['age_bin'] = pd.cut(df['Age'], bins=[x for x in age_bins],
                           labels=age_bin_labels)
    df['asexual_parasites'] = [x for x in df['Parasitemia']]
    df['density_bin'] = pd.cut(df['Parasitemia'], bins=pfprBins, labels=density_bin_edges)
    df['gametocytes'] = [x for x in df['Gametocytemia']]

    survey_summary_df = pd.DataFrame(columns=['month', 'age_bin', 'density_bin', 'count'])

    for index, age_density_subset in df.groupby(['age_bin', 'density_bin', 'Seasons']):
        subset_df = pd.DataFrame({
            'month': [index[2]],
            'age_bin': [index[0]],
            'density_bin': [index[1]],
            'count': [max(age_density_subset.shape[0], 0)]
        })
        survey_summary_df = pd.concat([survey_summary_df, subset_df])
    all_surveys_ref_df = pd.concat([all_surveys_ref_df, survey_summary_df])
    all_surveys_ref_df = all_surveys_ref_df[all_surveys_ref_df['month'].isin(['DH2', 'W2', 'DC2'])]
    return all_surveys_ref_df

class Survey_Prevalence_by_Age_and_Density_Analyzer(BaseAnalyzer):

    def __init__(self,dates,verbose_plotting):
        super().__init__(filenames=['output/MalariaSurveyJSONAnalyzer_Day_%d_0.json' %x for x in dates])
        self.dates = dates
        self.verbose_plotting = verbose_plotting
        self.metadata =  {
        'density_bins': [-1, 0, 50, 200, 500, np.inf],  # (, 0] (0, 50] ... (50000, ]
        'density_bin_edges':['-1', '0', '50', '200', '500'],
        'age_bins': [0, 1, 4, 8, 18, 28, 43, np.inf],  # (, 5] (5, 15] (15, ],
        'age_bin_labels':['<1', '1-4', '4-8', '8-18', '18-28', '28-43', '>43'],
        'survey_days':[365 * (years - 1) + x for x in np.arange(0, 365, 30)],
        'seasons': ['DC2', 'DH2', 'W2'],
        'seasons_by_month': {
            'Apr': 'DH2',
            'June/Aug': 'W2',
            'Dec/Jan': 'DC2'
        },
        'village': 'Sugungum'
    }

    def select_simulation_data(self, data, simulation):
        aEIR = simulation.tags['annual EIR']
        years = simulation.tags['sim_duration_years']
        months = [
            'DC2',
            'Feb',
            'Mar',
            'Apr',
            'DH2',
            'Jun',
            'Jul',
            'Aug',
            'W2',
            'Oct',
            'Nov',
            'Dec'
        ]

        age_bins = self.metadata['age_bins']
        age_bin_labels = self.metadata['age_bin_labels']

        density_bins = self.metadata['density_bins']
        density_bin_edges = self.metadata['density_bin_edges']

        survey_days = self.metadata['survey_days']

        #loop through survey_report days
        all_surveys_df = pd.DataFrame(columns=['survey','age_bin','density_bin','count'])
        for day in range(len(survey_days)):

            survey_data = data[self.filenames[day]]
            numeric_day = int(self.filenames[day][-10:-7])
            #loop through age_bins and then calculate the analyzer metrics across individuals
            #individuals true ages will betheir initial birthday plus time until report!
            df = pd.DataFrame([x for x in survey_data['patient_array']])
            df['age_bin'] = pd.cut(df['initial_age'], bins=[365 * x for x in age_bins],
                                   labels=age_bin_labels)

            df['asexual_parasites'] = [x[0] for x in df['asexual_parasites']]
            df['density_bin'] = pd.cut(df['asexual_parasites'],bins = density_bins,labels = density_bin_edges)
            df['gametocytes'] = [x[0] for x in df['gametocytes']]
            df['asexual_positive'] = [bool(x>100) for x in df['asexual_parasites']]

            survey_summary_df = pd.DataFrame(columns=['survey','month','age_bin', 'density_bin', 'count'])

            for index, age_density_subset in df.groupby(['age_bin','density_bin']):
                subset_df = pd.DataFrame({
                        'survey':[survey_days[day]],
                        'month': [months[day % 12]],
                        'age_bin':[index[0]],
                        'density_bin':[index[1]],
                        'count': [max(age_density_subset.shape[0],0)]
                    })
                survey_summary_df = pd.concat([survey_summary_df,subset_df])
            all_surveys_df = pd.concat([all_surveys_df,survey_summary_df])



        return {'aEIR': aEIR,
                'sim_df': all_surveys_df,
                'years': years,
                'age_bins': age_bins,
                'parasitemia_bins': density_bins,
                'survey_days':survey_days

                }
    def finalize(self, all_data):
        # first extract the age bins from the reference data structure
        cmap = [
            '#3498DB',
            '#1ABC9C',
            '#16A085',
            '#27AE60',
            '#2ECC71',
            '#F1C40F',
            '#F39C12',
            '#E67E22',
            '#D35400',
            '#C0392B',
            '#8E44AD',
            '#2980B9']
        months = [
            'Jan',
            'Feb',
            'Mar',
            'Apr',
            'May',
            'Jun',
            'Jul',
            'Aug',
            'Sep',
            'Oct',
            'Nov',
            'Dec'
        ]
        ref_data = get_reference_data(self)
        #columns that I want are survey/month, age_bin, density_bin, count

        #want to plot the reference data on the same axes as the sim binned data
        #want to calc a distance metric between sim and ref (dirch multi?)

        results = pd.DataFrame()

        for sim, data in all_data.items():
            #for each sim I want to group by each age bin and then calculate a mean infection duration and then append to a dataframe a row that has the columns:
            # sample. simid. category. and value from sim

            sample = sim.tags.get("__sample_index__")
            sim_id = sim.id
            for age in range(len(age_bins[:-1])):
                sim_subset = data[(data['initial_age'] >= age_bins[age])&(data['initial_age'] < age_bins[age+1])]
                simulation_durations = []
                for iid, patient in sim_subset.iterrows():
                    (positive_day_indices,) = np.where(np.array(patient['true_asexual_parasites'][0]) > 0)
                    try:
                        simulation_durations.append(max(positive_day_indices))
                    except:
                        print(iid, age_bins[age], sim_id)

                age_cat = f'{age_bins[age]/365}-{age_bins[age+1]/365}'
                value = np.mean(simulation_durations)
                sub_results = pd.DataFrame({'sample' : sample,
                                            'sim_id': sim_id,
                                            'age_cat': age_cat,
                                            'value': [value]})
                #Could log the individual id, ind age and ind duration.

                results = pd.concat([results,sub_results])
            #loop through all the age bins
            #evaluate their mean duration for each age bin
        results.to_csv(os.path.join('..', 'iter0', 'analyzer_results.csv'))

        for sim, data in all_data.items():
            eir = data['aEIR']
            exp_name = sim.experiment.exp_name
            age_bin_labels = self.metadata['age_bin_labels']

            counts_by_age_and_density_bin = data['sim_df']
            counts_by_age_and_density_bin.reset_index(drop=True, inplace=True)
            counts_by_age_and_density_bin = counts_by_age_and_density_bin[counts_by_age_and_density_bin.month.isin(self.metadata['seasons'])]

            #remove the first January from sim data, as data are reflected from the subsequent Jan in DC2

            counts_by_age_and_density_bin.drop(
                counts_by_age_and_density_bin[counts_by_age_and_density_bin['survey'] == 730].index, inplace=True)

            counts_by_age_and_density_bin.drop(columns='survey', inplace=True)
            df2 = pd.merge(ref_data, counts_by_age_and_density_bin, on=['age_bin', 'density_bin', 'month'])

            df2['ref_bin_pop'] = df2.groupby(['month', 'age_bin']).transform(lambda x: x.sum())['count_x']
            df2['sim_bin_pop'] = df2.groupby(['month', 'age_bin']).transform(lambda x: x.sum())['count_y']
            df2['ref'] = df2['count_x']/df2['ref_bin_pop']
            df2['sim'] = df2['count_y'] / df2['sim_bin_pop']
            # df3 = df2[df2['month', 'age_bin', 'density_bin'],:]
            # df3.set_index(['month', 'age_bin', 'density_bin'], inplace=True)
            # LL = dirichlet_multinomial_pandas_mod(df3)

            df2['diff'] = df2['sim']-df2['ref']
            norm = np.linalg.norm(df2['diff'],ord = 1)

            # new_df = pd.merge(A_df, B_df, how='left', left_on=['A_c1', 'c2'], right_on=['B_c1', 'c2'])
            g = sns.FacetGrid(df2, col="month", row="age_bin")
            g = g.map(plt.plot, "density_bin", "ref", marker='.', markersize=20, color='r')
            g = g.map(plt.plot, "density_bin", "sim", marker='x', markersize=20, color='b')

            plt.suptitle(f'PfPR by Season (col), Age (row) and Density Bin (x), aEIR ={eir}')
            sim_dir_path = os.path.join(os.path.expanduser('~'), 'Dropbox (IDM)', 'Malaria Team Folder', 'projects',
                                        'updated_infection_and_immunity',
                                        'malaria-two-pt-oh', 'figures', 'Simulation_Sanity_Checks',
                                        f'{exp_name}-eir{int(eir)}')

            if not os.path.exists(sim_dir_path):
                os.mkdir(sim_dir_path)
            plt.savefig(os.path.join(sim_dir_path,
                                     'pfpr_by_age_bin_and density_bin_by_month.png'))
            if self.verbose_plotting == True:
                plt.show()
            else:
                plt.clf()
            sub_results = pd.DataFrame({'sample': sample,
                                        'sim_id': sim_id,
                                        'age_cat': age_cat,
                                        'value': [value]})
            results = pd.concat([results, sub_results])


        ######


if __name__ == '__main__':
    years = 3
    survey_days = [365 * (years - 1) + x for x in np.arange(0, 365, 30)]
    am = AnalyzeManager('latest',analyzers=Survey_Prevalence_by_Age_and_Density_Analyzer(dates = survey_days,verbose_plotting=True))
    am.analyze()
