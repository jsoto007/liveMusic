/**
 * The tab bar and stack.
 *
 * Five tabs, matching the prototype: Bill, Map, Post (the ringed centre
 * action), List, You. Search is a header action on the Bill rather than a
 * sixth tab, which is where the prototype puts it. Headers are the paper's
 * masthead — the heading face on the ground colour with a hairline rule,
 * never a filled bar.
 */

import { NavigationContainer, type Theme } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { StyleSheet, View } from "react-native";
import { Bookmark, MapPin, Newspaper, Plus, User } from "lucide-react-native";

import { AccountScreen } from "../screens/AccountScreen";
import { JoinScreen, SignInScreen } from "../screens/AuthScreens";
import { BandScreen } from "../screens/BandScreen";
import { BillScreen } from "../screens/BillScreen";
import { ListScreen } from "../screens/ListScreen";
import { PlanScreen } from "../screens/PlanScreen";
import { PostScreen } from "../screens/PostScreen";
import { SearchScreen } from "../screens/SearchScreen";
import { ShowScreen } from "../screens/ShowScreen";
import { colors, fonts, ink } from "../lib/theme";
import type { RootStackParamList, TabParamList } from "./types";

const Tab = createBottomTabNavigator<TabParamList>();
const Stack = createNativeStackNavigator<RootStackParamList>();

// The shared icon footprint, and the centre ring's diameter — the same number
// by design, so the ring can never outgrow its slot and overprint its label.
const POST_RING_SIZE = 30;

const navigationTheme: Theme = {
  dark: false,
  colors: {
    primary: colors.accent,
    background: colors.bg,
    card: colors.bg,
    text: colors.text,
    border: ink.divider,
    notification: colors.accent,
  },
};

const headerOptions = {
  headerStyle: { backgroundColor: colors.bg },
  headerTitleStyle: { fontFamily: fonts.heading, fontSize: 18, color: colors.text },
  headerTintColor: colors.accent,
  headerShadowVisible: false,
  // Without this the back button inherits the previous route's name and reads
  // "Tabs" — an internal identifier, not something to show a reader.
  headerBackTitle: "Back",
} as const;

/** The centre action: an outlined ring, the one drawn emphasis in the bar.
 *
 * Sized to exactly fill the shared icon slot (see `tabBarIconStyle`). At 38px
 * it overflowed a slot laid out for the 20px icons and the ring's stroke ran
 * straight through the word "POST" underneath it. */
function PostTabIcon({ color }: { color: string }) {
  return (
    <View style={[styles.postRing, { borderColor: color }]}>
      <Plus size={16} color={color} strokeWidth={1.4} />
    </View>
  );
}

function Tabs() {
  return (
    <Tab.Navigator
      screenOptions={{
        // Each tab screen prints its own editorial header — the display cut on
        // the ground colour with a hairline under it. A chrome bar above that
        // would repeat every title and is not what the design does.
        headerShown: false,
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: ink.ghost,
        tabBarStyle: {
          backgroundColor: colors.bg,
          borderTopWidth: StyleSheet.hairlineWidth,
          borderTopColor: ink.divider,
          // No fixed height: React Navigation sizes the bar from the safe-area
          // inset, and hard-coding it clipped the labels on a device with a
          // home indicator.
          paddingTop: 9,
        },
        // One icon footprint for every tab. Without it the slot is sized by
        // its own icon, so the centre ring — deliberately larger than the
        // line icons — pushed down past the others and printed over its own
        // label. Now the ring fills this box and the 20px icons centre in it,
        // so all five labels sit on the same baseline.
        tabBarIconStyle: { height: POST_RING_SIZE, justifyContent: "center" },
        tabBarLabelStyle: {
          fontFamily: fonts.body,
          fontSize: 9,
          letterSpacing: 1,
          textTransform: "uppercase",
        },
      }}
    >
      <Tab.Screen
        name="Bill"
        component={BillScreen}
        options={{
          title: "Live Msc",
          tabBarLabel: "Bill",
          tabBarIcon: ({ color }) => <Newspaper size={20} color={color} strokeWidth={1.4} />,
        }}
      />
      <Tab.Screen
        name="Plan"
        component={PlanScreen}
        options={{
          title: "The Plan",
          tabBarLabel: "Map",
          tabBarIcon: ({ color }) => <MapPin size={20} color={color} strokeWidth={1.4} />,
        }}
      />
      <Tab.Screen
        name="Post"
        component={PostScreen}
        options={{
          title: "Post a show",
          tabBarLabel: "Post",
          tabBarIcon: ({ color }) => <PostTabIcon color={color} />,
        }}
      />
      <Tab.Screen
        name="List"
        component={ListScreen}
        options={{
          title: "Your list",
          tabBarLabel: "List",
          tabBarIcon: ({ color }) => <Bookmark size={20} color={color} strokeWidth={1.4} />,
        }}
      />
      <Tab.Screen
        name="You"
        component={AccountScreen}
        options={{
          title: "Your account",
          tabBarLabel: "You",
          tabBarIcon: ({ color }) => <User size={20} color={color} strokeWidth={1.4} />,
        }}
      />
    </Tab.Navigator>
  );
}

export function Navigation() {
  return (
    <NavigationContainer theme={navigationTheme}>
      <Stack.Navigator screenOptions={headerOptions}>
        <Stack.Screen name="Tabs" component={Tabs} options={{ headerShown: false }} />
        <Stack.Screen name="Show" component={ShowScreen} options={{ title: "A show" }} />
        <Stack.Screen name="Band" component={BandScreen} options={{ title: "A band" }} />
        <Stack.Screen name="Search" component={SearchScreen} options={{ title: "Look it up" }} />
        <Stack.Screen
          name="SignIn"
          component={SignInScreen}
          options={{ title: "Sign in", presentation: "modal" }}
        />
        <Stack.Screen
          name="Join"
          component={JoinScreen}
          options={{ title: "Join", presentation: "modal" }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  postRing: {
    width: POST_RING_SIZE,
    height: POST_RING_SIZE,
    borderRadius: POST_RING_SIZE / 2,
    borderWidth: StyleSheet.hairlineWidth * 2,
    alignItems: "center",
    justifyContent: "center",
  },
});
