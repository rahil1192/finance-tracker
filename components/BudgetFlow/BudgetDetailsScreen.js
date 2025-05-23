import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  ScrollView,
  Switch,
} from 'react-native';
import Slider from '@react-native-community/slider';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation, useRoute } from '@react-navigation/native';

export default function BudgetDetailsScreen() {
  const navigation = useNavigation();
  const route = useRoute();
  const { budgetType } = route.params || { budgetType: 'Expense' };
  
  const [budgetName, setBudgetName] = useState('');
  const [budgetAmount, setBudgetAmount] = useState('');
  const [rolloverBudget, setRolloverBudget] = useState(false);
  const [alertPercentage, setAlertPercentage] = useState(70);

  const handleNext = () => {
    navigation.navigate('BudgetReviewScreen', {
      budgetType,
      budgetName: budgetName || 'Hi',
      budgetAmount: budgetAmount || '45',
      repeatFrequency: 'Every Month',
      startDate: 'May 1',
      rolloverBudget,
      alertPercentage,
    });
  };

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity 
          onPress={() => navigation.goBack()} 
          style={styles.backButton}
        >
          <Ionicons name="arrow-back" size={24} color="#0284c7" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Create Budget</Text>
        <View style={styles.placeholderView} />
      </View>

      <ScrollView style={styles.content}>
        {/* Budget Type */}
        <View style={styles.typeContainer}>
          <Text style={styles.typeLabel}>Type</Text>
          <Text style={styles.typeValue}>{budgetType}</Text>
        </View>

        {/* Budget Name */}
        <View style={styles.inputRow}>
          <View style={styles.iconContainer}>
            <Ionicons name="wallet-outline" size={24} color="#64748b" />
          </View>
          <TextInput
            style={styles.input}
            placeholder="Budget Name"
            placeholderTextColor="#9ca3af"
            value={budgetName}
            onChangeText={setBudgetName}
          />
          <TouchableOpacity>
            <Ionicons name="camera" size={24} color="#0284c7" />
          </TouchableOpacity>
        </View>
        <View style={styles.separator} />

        {/* Budget Amount */}
        <View style={styles.inputRow}>
          <View style={styles.iconContainer}>
            <Text style={styles.iconText}>$</Text>
          </View>
          <TextInput
            style={styles.input}
            placeholder="Budget Amount"
            placeholderTextColor="#9ca3af"
            keyboardType="decimal-pad"
            value={budgetAmount}
            onChangeText={setBudgetAmount}
          />
        </View>
        <View style={styles.separator} />

        {/* Repeat Frequency */}
        <TouchableOpacity style={styles.inputRow}>
          <View style={styles.iconContainer}>
            <Ionicons name="refresh-outline" size={24} color="#64748b" />
          </View>
          <View style={styles.repeatContainer}>
            <Text style={styles.inputText}>Repeats Every Month</Text>
            <Text style={styles.inputText}>Starting May 1</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color="#0284c7" />
        </TouchableOpacity>
        <View style={styles.separator} />

        {/* Categories */}
        <TouchableOpacity style={styles.inputRow}>
          <View style={styles.iconContainer}>
            <Ionicons name="grid-outline" size={24} color="#64748b" />
          </View>
          <View style={styles.categoriesContainer}>
            <Text style={styles.placeholderText}>Select Categories</Text>
            <Text style={styles.helperText}>All categories are included if not selected any.</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color="#0284c7" />
        </TouchableOpacity>
        <View style={styles.separator} />

        {/* Accounts */}
        <TouchableOpacity style={styles.inputRow}>
          <View style={styles.iconContainer}>
            <Ionicons name="business-outline" size={24} color="#64748b" />
          </View>
          <View style={styles.categoriesContainer}>
            <Text style={styles.placeholderText}>Select Accounts</Text>
            <Text style={styles.helperText}>All accounts are included if not selected any.</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color="#0284c7" />
        </TouchableOpacity>
        <View style={styles.separator} />

        {/* Rollover Budget */}
        <View style={styles.inputRow}>
          <View style={styles.iconContainer}>
            <Ionicons name="arrow-forward-outline" size={24} color="#64748b" />
          </View>
          <Text style={styles.inputText}>Rollover budget amount</Text>
          <View style={styles.infoContainer}>
            <Ionicons name="information-circle-outline" size={20} color="#64748b" />
          </View>
          <Switch
            value={rolloverBudget}
            onValueChange={setRolloverBudget}
            trackColor={{ false: "#e5e7eb", true: "#0284c7" }}
            thumbColor="#ffffff"
          />
        </View>
        <View style={styles.separator} />

        {/* Alert Percentage */}
        <View style={styles.alertContainer}>
          <View style={styles.alertHeader}>
            <View style={styles.alertIconContainer}>
              <Ionicons name="notifications-outline" size={24} color="#64748b" />
            </View>
            <Text style={styles.alertText}>
              Alert me when expense reaches <Text style={styles.boldText}>70%</Text> of budget
            </Text>
          </View>
          <Slider
            style={styles.slider}
            minimumValue={0}
            maximumValue={100}
            step={5}
            value={alertPercentage}
            onValueChange={setAlertPercentage}
            minimumTrackTintColor="#0284c7"
            maximumTrackTintColor="#e5e7eb"
            thumbTintColor="#0284c7"
          />
        </View>

        {/* Next Button */}
        <TouchableOpacity 
          style={styles.nextButton}
          onPress={handleNext}
        >
          <Text style={styles.nextButtonText}>NEXT</Text>
          <Ionicons name="chevron-forward" size={20} color="white" />
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: 'white',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#e0f2fe',
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#1e293b',
  },
  backButton: {
    padding: 4,
  },
  placeholderView: {
    width: 32,
  },
  content: {
    flex: 1,
    paddingBottom: 24,
  },
  typeContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 16,
    backgroundColor: 'white',
    borderRadius: 16,
    marginHorizontal: 16,
    marginTop: 16,
  },
  typeLabel: {
    fontSize: 16,
    color: '#94a3b8',
    marginRight: 8,
  },
  typeValue: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#1e293b',
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 16,
    paddingHorizontal: 16,
  },
  iconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#f1f5f9',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  iconText: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#64748b',
  },
  input: {
    flex: 1,
    fontSize: 16,
    color: '#1e293b',
  },
  placeholderText: {
    fontSize: 16,
    color: '#9ca3af',
  },
  inputText: {
    fontSize: 16,
    color: '#1e293b',
  },
  repeatContainer: {
    flex: 1,
  },
  categoriesContainer: {
    flex: 1,
  },
  helperText: {
    fontSize: 14,
    color: '#94a3b8',
    marginTop: 4,
  },
  separator: {
    height: 1,
    backgroundColor: '#e2e8f0',
    marginLeft: 68,
  },
  infoContainer: {
    marginRight: 8,
  },
  alertContainer: {
    padding: 16,
    backgroundColor: 'white',
    borderRadius: 16,
    margin: 16,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  alertHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  alertIconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#f1f5f9',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  alertText: {
    flex: 1,
    fontSize: 16,
    color: '#1e293b',
  },
  boldText: {
    fontWeight: 'bold',
  },
  slider: {
    width: '100%',
    height: 40,
  },
  nextButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#0284c7',
    borderRadius: 8,
    paddingVertical: 16,
    marginHorizontal: 16,
    marginTop: 24,
    marginBottom: 40,
  },
  nextButtonText: {
    fontSize: 16,
    fontWeight: 'bold',
    color: 'white',
    marginRight: 8,
  },
});